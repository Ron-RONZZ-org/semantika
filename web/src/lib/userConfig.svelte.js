/**
 * User configuration store — locale, preferences.
 * Syncs with backend on init.
 */

let _locale = $state("en");

/** Initialize locale from backend, falling back to browser language. */
export async function initLocale() {
  // Try browser language first
  const browserLang = navigator.language || navigator.languages?.[0] || "en";

  try {
    const resp = await fetch("/api/v1/user/config");
    if (resp.ok) {
      const data = await resp.json();
      _locale = data.locale || browserLang;
    } else {
      _locale = browserLang;
    }
  } catch {
    _locale = browserLang;
  }

  // Sync browser locale to backend if different
  const code = _locale.slice(0, 2);
  try {
    await fetch("/api/v1/user/config", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locale: code }),
    });
  } catch { /* silent */ }
  _locale = code;
}

/** Set locale on both frontend and backend. */
export async function setLocale(code) {
  _locale = code.slice(0, 2);
  try {
    await fetch("/api/v1/user/config", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ locale: _locale }),
    });
  } catch { /* silent */ }
}

export function getLocale() {
  return _locale;
}
