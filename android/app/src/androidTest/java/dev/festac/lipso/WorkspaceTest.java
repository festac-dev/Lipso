package dev.festac.lipso;

import android.graphics.Bitmap;
import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.ContentValues;
import android.content.ContentResolver;
import android.net.Uri;
import android.provider.MediaStore;
import android.webkit.WebView;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class WorkspaceTest {
    private String evaluate(ActivityScenario<MainActivity> scenario, String javascript) throws Exception {
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<String> value = new AtomicReference<>();
        scenario.onActivity(activity -> {
            WebView view = activity.workspaceView();
            if (view == null) { latch.countDown(); return; }
            view.evaluateJavascript(javascript, result -> { value.set(result); latch.countDown(); });
        });
        assertTrue("WebView did not respond", latch.await(10, TimeUnit.SECONDS));
        return value.get();
    }

    private void waitFor(ActivityScenario<MainActivity> scenario, String expression) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
        while (System.nanoTime() < deadline) {
            if ("true".equals(evaluate(scenario, expression))) return;
            Thread.sleep(250);
        }
        fail("Timed out: " + expression + "; page: " + evaluate(scenario, "document.body.innerText.slice(0, 600)"));
    }

    private void screenshot(String name) throws Exception {
        // MediaStore downloads survive Gradle uninstalling the test app.
        // These captures contain only this test's fictional sample records.
        ContentResolver resolver = InstrumentationRegistry.getInstrumentation().getTargetContext().getContentResolver();
        ContentValues values = new ContentValues();
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
        values.put(MediaStore.MediaColumns.MIME_TYPE, "image/png");
        values.put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/lipso-screenshots");
        Uri target = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        assertNotNull(target);
        Bitmap bitmap = InstrumentationRegistry.getInstrumentation().getUiAutomation().takeScreenshot();
        assertNotNull(bitmap);
        try (OutputStream out = resolver.openOutputStream(target)) {
            assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, out));
        }
        bitmap.recycle();
    }

    private void checkSavePicker(ActivityScenario<MainActivity> scenario, String trigger) throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        IntentFilter filter = new IntentFilter(Intent.ACTION_CREATE_DOCUMENT);
        filter.addCategory(Intent.CATEGORY_OPENABLE);
        filter.addDataType("*/*");
        Instrumentation.ActivityMonitor monitor = instrumentation.addMonitor(filter,
            new Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null), true);
        try {
            evaluate(scenario, trigger);
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
            while (monitor.getHits() == 0 && System.nanoTime() < deadline) Thread.sleep(100);
            assertEquals("Native export did not reach the Save as picker", 1, monitor.getHits());
            instrumentation.waitForIdleSync();
        } finally { instrumentation.removeMonitor(monitor); }
    }

    @Test public void offlineWorkspaceSurvivesReopen() throws Exception {
        try (ActivityScenario<MainActivity> scenario = ActivityScenario.launch(MainActivity.class)) {
            waitFor(scenario, "!!document.querySelector('[data-action=demo]')");
            assertEquals("6.4.2", com.chaquo.python.Python.getInstance().getModule("pypdf").get("__version__").toString());
            String base = new org.json.JSONArray("[" + evaluate(scenario, "location.origin") + "]").getString(0);
            HttpURLConnection unauthenticated = (HttpURLConnection) new URL(base + "/api/state").openConnection();
            try { assertEquals(403, unauthenticated.getResponseCode()); }
            finally { unauthenticated.disconnect(); }
            evaluate(scenario, "document.querySelector('[data-action=demo]').click()");
            waitFor(scenario, "document.body.innerText.includes('Two versions of monthly rent.')");
            evaluate(scenario, "document.documentElement.dataset.theme !== 'light' && document.querySelector('#theme-toggle').click()");
            screenshot("android-overview-light.png");
            // Exercise the actual Android Python, SQLite FTS5, pypdf import,
            // document store, planner, ZIP/ICS endpoints and HttpOnly cookie.
            evaluate(scenario, "window.smoke='pending'; (async () => { try {"
                + "const headers={'Content-Type':'application/json','X-Lipso-Client':'workspace'};"
                + "const r=await fetch('/api/documents',{method:'POST',headers,body:JSON.stringify({filename:'android-check.txt',matter:'Android check',content_base64:btoa('Invoice total: USD 73.00. Payment due 2027-03-15. Quasar evidence.')})});"
                + "if(r.status!==201) throw Error('import '+r.status); const doc=await r.json();"
                + "const found=await (await fetch('/api/search?q=Quasar')).json(); if(!found.results.length) throw Error('FTS5');"
                + "const original=await (await fetch('/api/documents/'+doc.id+'/original')).text(); if(!original.includes('Quasar')) throw Error('original');"
                + "const plans=await (await fetch('/api/plans')).json(); const plan=await (await fetch('/api/plans/'+plans.plans[0].id)).json();"
                + "const sim=await fetch('/api/simulate',{method:'POST',headers,body:JSON.stringify({data:plan.data})}); if(!sim.ok) throw Error('simulation');"
                + "for(const path of ['/api/export','/api/calendar']) { const res=await fetch(path); if(!res.ok || !(await res.arrayBuffer()).byteLength) throw Error(path); }"
                + "await fetch('/api/documents/'+doc.id,{method:'DELETE',headers});"
                + "const integrity=await (await fetch('/api/integrity')).json(); if(!integrity.ok) throw Error('integrity');"
                + "if(document.cookie.includes('lipso_session')) throw Error('cookie visible');"
                + "window.smoke='ok'; } catch(e) {window.smoke='ERROR: '+e.message;} })()");
            waitFor(scenario, "window.smoke !== 'pending'");
            assertEquals("\"ok\"", evaluate(scenario, "window.smoke"));
            evaluate(scenario, "document.querySelector('#theme-toggle').click()");
            waitFor(scenario, "document.documentElement.dataset.theme === 'dark'");
            screenshot("android-overview-dark.png");
            evaluate(scenario, "document.querySelector('[data-action=menu]').click()");
            waitFor(scenario, "document.body.classList.contains('nav-open')");
            screenshot("android-navigation-dark.png");
            scenario.onActivity(MainActivity::onBackPressed);
            waitFor(scenario, "!document.body.classList.contains('nav-open')");
            scenario.recreate();
            waitFor(scenario, "document.body.innerText.includes('Two versions of monthly rent.')");
            assertEquals("\"dark\"", evaluate(scenario, "document.documentElement.dataset.theme"));
            evaluate(scenario, "document.querySelector('[data-view=plans]').click()");
            waitFor(scenario, "document.body.innerText.includes('A range of tomorrows')");
            screenshot("android-planning-dark.png");
            checkSavePicker(scenario, "document.querySelector('[data-action=export-plan]').click()");
            checkSavePicker(scenario, "document.querySelector('[data-action=export]').click()");
        }
    }
}
