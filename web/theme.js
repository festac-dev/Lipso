// Apply the preference before the stylesheet paints to avoid a light flash.
(() => {
  // Retain the existing key so the Lipso rename preserves the selected theme.
  const storageKey = 'margin.theme';
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  const validTheme = value => value === 'light' || value === 'dark' ? value : null;
  let preference = null;
  try { preference = validTheme(localStorage.getItem(storageKey)); } catch { /* Storage may be disabled. */ }

  function applyTheme() {
    const theme = preference || (systemTheme.matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === 'dark' ? '#101713' : '#fafbf7';
    const toggle = document.getElementById('theme-toggle');
    if (toggle) {
      const label = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
      toggle.setAttribute('aria-label', label);
      toggle.title = label;
    }
  }

  applyTheme();
  document.addEventListener('DOMContentLoaded', applyTheme);
  document.addEventListener('click', event => {
    if (!event.target.closest('#theme-toggle')) return;
    preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(storageKey, preference); } catch { /* Still switch for this visit. */ }
    applyTheme();
  });
  systemTheme.addEventListener('change', () => { if (!preference) applyTheme(); });
  window.addEventListener('storage', event => {
    if (event.key === storageKey || event.key === null) {
      preference = validTheme(event.newValue);
      applyTheme();
    }
  });
})();
