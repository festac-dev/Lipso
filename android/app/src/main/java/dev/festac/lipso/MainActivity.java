package dev.festac.lipso;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final int OPEN_DOCUMENT = 10, SAVE_DOCUMENT = 11;
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private WebView webView;
    private FrameLayout root;
    private TextView status;
    private String baseUrl, sessionCookie;
    private ValueCallback<Uri[]> fileChooser;
    private File pendingExport;
    private boolean exporting;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(35, 75, 59));
        setContentView(root);
        // Android 15 enforces edge-to-edge. Keep controls clear of system bars
        // and the keyboard while preserving the webpage's own scroll container.
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets area = insets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                view.setPadding(area.left, area.top, area.right, area.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        status = new TextView(this);
        status.setText("Opening Lipso…");
        status.setTextColor(Color.WHITE);
        status.setTextSize(18);
        status.setGravity(Gravity.CENTER);
        root.addView(status, new FrameLayout.LayoutParams(-1, -1));
        if (state != null && state.getString("pendingExport") != null) {
            File saved = new File(getCacheDir(), state.getString("pendingExport"));
            if (saved.isFile() && saved.getName().startsWith("lipso-export-")) {
                pendingExport = saved;
                exporting = true;
            }
        }
        WORKER.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                PyObject session = Python.getInstance().getModule("mobile")
                    .callAttr("start", getFilesDir().getAbsolutePath());
                String url = session.get("url").toString();
                String cookie = "lipso_session=" + session.get("token").toString();
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    baseUrl = url;
                    sessionCookie = cookie;
                    openWorkspace();
                });
            } catch (Exception error) {
                android.util.Log.e("Lipso", "Workspace startup failed", error);
                runOnUiThread(() -> {
                    if (!isDestroyed()) status.setText("Lipso could not open the workspace.\nClose and reopen the app to try again.");
                });
            }
        });
    }

    @SuppressWarnings("SetJavaScriptEnabled")
    private void openWorkspace() {
        webView = new WebView(this);
        webView.setId(View.generateViewId());
        webView.setBackgroundColor(Color.rgb(250, 251, 247));
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // System document picker only.
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        webView.addJavascriptInterface(new AppBridge(), "LipsoAndroid");
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !isLocal(request.getUrl().toString());
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                if (isLocal(request.getUrl().toString())) return null;
                return new WebResourceResponse("text/plain", "UTF-8", 403, "Blocked", null,
                    new ByteArrayInputStream(new byte[0]));
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (isLocal(url)) status.setVisibility(View.GONE);
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileChooser != null) fileChooser.onReceiveValue(null);
                fileChooser = callback;
                Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT)
                    .addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");
                picker.putExtra(Intent.EXTRA_MIME_TYPES, new String[] { "application/pdf", "text/*",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream" });
                try { startActivityForResult(picker, OPEN_DOCUMENT); }
                catch (ActivityNotFoundException error) {
                    fileChooser.onReceiveValue(null);
                    fileChooser = null;
                    message("No document picker is available.");
                }
                return true;
            }
        });
        webView.setDownloadListener((url, agent, disposition, mime, length) -> {
            if (!isExportUrl(url)) { message("This download is not supported."); return; }
            String name = URLUtil.guessFileName(url, disposition, mime);
            if (disposition != null && disposition.startsWith("attachment; filename*=UTF-8''")) {
                try { name = URLDecoder.decode(disposition.substring(disposition.indexOf("''") + 2), "UTF-8"); }
                catch (Exception ignored) { /* Keep the system's suggested name. */ }
            }
            prepareExport(url, null, name, mime);
        });
        root.addView(webView, 0, new FrameLayout.LayoutParams(-1, -1));
        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, false);
        cookies.setCookie(baseUrl, sessionCookie + "; Path=/; HttpOnly; SameSite=Strict", accepted -> {
            if (!isDestroyed()) webView.loadUrl(baseUrl + "/");
        });
    }

    private boolean isLocal(String url) {
        if (baseUrl == null) return false;
        Uri uri = Uri.parse(url), base = Uri.parse(baseUrl);
        return "http".equals(uri.getScheme()) && "127.0.0.1".equals(uri.getHost())
            && uri.getPort() == base.getPort() && uri.getUserInfo() == null;
    }

    private boolean isExportUrl(String url) {
        if (!isLocal(url)) return false;
        String path = Uri.parse(url).getPath();
        return "/api/export".equals(path) || "/api/calendar".equals(path)
            || (path != null && path.matches("/api/documents/[a-f0-9]{32}/original"));
    }

    public final class AppBridge {
        @JavascriptInterface public String getTheme() {
            return getSharedPreferences("appearance", MODE_PRIVATE).getString("theme", "");
        }
        @JavascriptInterface public void setTheme(String theme) {
            if ("light".equals(theme) || "dark".equals(theme)) {
                getSharedPreferences("appearance", MODE_PRIVATE).edit().putString("theme", theme).apply();
            }
        }
        @JavascriptInterface public void savePlan(String json) {
            if (json == null || json.length() > 8 * 1024 * 1024) { message("This plan is too large to export."); return; }
            try {
                new JSONObject(json);
                byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
                runOnUiThread(() -> prepareExport(null, bytes, "lipso-plan.json", "application/json"));
            } catch (Exception error) { message("The plan could not be exported."); }
        }
    }

    private void prepareExport(String url, byte[] bytes, String filename, String mime) {
        if (exporting) { message("Finish the current export first."); return; }
        exporting = true;
        String safeName = filename.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_");
        if (safeName.length() > 180) safeName = safeName.substring(0, 180);
        final String title = safeName;
        message("Preparing export…");
        WORKER.execute(() -> {
            File temporary = null;
            HttpURLConnection connection = null;
            try {
                temporary = File.createTempFile("lipso-export-", ".tmp", getCacheDir());
                if (bytes != null) {
                    try (OutputStream out = new FileOutputStream(temporary)) { out.write(bytes); }
                } else {
                    if (!isExportUrl(url)) throw new IllegalArgumentException("Invalid export URL");
                    connection = (HttpURLConnection) new URL(url).openConnection();
                    connection.setInstanceFollowRedirects(false);
                    connection.setConnectTimeout(15000);
                    connection.setReadTimeout(60000);
                    connection.setRequestProperty("Cookie", sessionCookie);
                    if (connection.getResponseCode() != 200) throw new java.io.IOException("Export failed");
                    try (InputStream in = connection.getInputStream(); OutputStream out = new FileOutputStream(temporary)) {
                        copy(in, out);
                    }
                }
                File ready = temporary;
                runOnUiThread(() -> {
                    if (isDestroyed()) { ready.delete(); return; }
                    pendingExport = ready;
                    Intent picker = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                        .setType(mime == null ? "application/octet-stream" : mime.split(";")[0])
                        .putExtra(Intent.EXTRA_TITLE, title);
                    try { startActivityForResult(picker, SAVE_DOCUMENT); }
                    catch (ActivityNotFoundException error) {
                        finishExport();
                        message("No document picker is available.");
                    }
                });
            } catch (Exception error) {
                if (temporary != null) temporary.delete();
                runOnUiThread(() -> { exporting = false; message("Export failed. Check available storage and try again."); });
            } finally { if (connection != null) connection.disconnect(); }
        });
    }

    private static void copy(InputStream in, OutputStream out) throws java.io.IOException {
        if (out == null) throw new java.io.IOException("No output stream");
        byte[] buffer = new byte[16384];
        int count;
        while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
    }

    private void finishExport() {
        if (pendingExport != null) pendingExport.delete();
        pendingExport = null;
        exporting = false;
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == OPEN_DOCUMENT && fileChooser != null) {
            Uri uri = result == RESULT_OK && data != null ? data.getData() : null;
            fileChooser.onReceiveValue(uri == null ? null : new Uri[] {uri});
            fileChooser = null;
        } else if (request == SAVE_DOCUMENT) {
            if (result != RESULT_OK || data == null || data.getData() == null) { finishExport(); return; }
            if (pendingExport == null) { exporting = false; message("Please start the export again."); return; }
            Uri target = data.getData();
            File source = pendingExport;
            WORKER.execute(() -> {
                try (InputStream in = new FileInputStream(source); OutputStream out = getContentResolver().openOutputStream(target, "wt")) {
                    copy(in, out);
                    message("Export saved.");
                } catch (Exception error) {
                    try { DocumentsContract.deleteDocument(getContentResolver(), target); } catch (Exception ignored) { }
                    message("Could not save the export. Check the destination and try again.");
                } finally { runOnUiThread(this::finishExport); }
            });
        }
    }

    @Override public void onBackPressed() {
        if (webView == null) { super.onBackPressed(); return; }
        webView.evaluateJavascript("(() => { const dialog = document.querySelector('dialog[open]');"
            + "if (dialog) { dialog.close(); return true; }"
            + "if (document.body.classList.contains('nav-open')) { document.querySelector('[data-action=close-menu]').click(); return true; }"
            + "return false; })()", handled -> {
                if (isDestroyed() || "true".equals(handled)) return;
                if (webView.canGoBack()) webView.goBack(); else MainActivity.super.onBackPressed();
            });
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        if (pendingExport != null) state.putString("pendingExport", pendingExport.getName());
    }

    @Override protected void onDestroy() {
        if (fileChooser != null) { fileChooser.onReceiveValue(null); fileChooser = null; }
        if (webView != null) {
            root.removeView(webView);
            webView.removeJavascriptInterface("LipsoAndroid");
            webView.destroy();
            webView = null;
        }
        // The daemon backend belongs to the process, so reopening the activity
        // does not interrupt imports or create a second database/server.
        super.onDestroy();
    }

    private void message(String text) {
        runOnUiThread(() -> { if (!isDestroyed()) Toast.makeText(this, text, Toast.LENGTH_LONG).show(); });
    }

    WebView workspaceView() { return webView; }
}
