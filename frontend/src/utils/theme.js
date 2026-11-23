export function setTheme(theme) {
  try {
    if (theme === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }
    localStorage.setItem('smp_theme', theme);
  } catch (e) {
    console.warn('Could not set theme', e);
  }
}

export function getTheme() {
  try {
    return localStorage.getItem('smp_theme') || 'dark';
  } catch (e) {
    return 'dark';
  }
}

export function initTheme() {
  const theme = getTheme();
  setTheme(theme);
}
