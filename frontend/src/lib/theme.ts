export const THEME_STORAGE_KEY = "smartsales-theme";
export const THEME_PREFERENCES = ["system", "light", "dark"] as const;
export type ThemePreference = (typeof THEME_PREFERENCES)[number];

const DARK_QUERY = "(prefers-color-scheme: dark)";
const THEME_CHANGE_EVENT = "smartsales-theme-change";

// Kept when storage is blocked (private mode, disabled site data), so the toggle still reflects the choice.
let unsavedPreference: ThemePreference = "system";

const isPreference = (value: unknown): value is ThemePreference =>
  THEME_PREFERENCES.includes(value as ThemePreference);

export function readThemePreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(stored) ? stored : "system";
  } catch {
    return unsavedPreference;
  }
}

const systemPrefersDark = (): boolean => window.matchMedia?.(DARK_QUERY).matches ?? false;

export function applyThemePreference(preference: ThemePreference): void {
  const dark = preference === "dark" || (preference === "system" && systemPrefersDark());
  document.documentElement.classList.toggle("dark", dark);
}

export function selectThemePreference(preference: ThemePreference): void {
  unsavedPreference = preference;
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // Storage blocked: the choice lasts for this page only.
  }
  applyThemePreference(preference);
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
}

export function subscribeThemePreference(onChange: () => void): () => void {
  window.addEventListener(THEME_CHANGE_EVENT, onChange);
  return () => window.removeEventListener(THEME_CHANGE_EVENT, onChange);
}

/** While on "system", keeps `.dark` in sync with the OS setting. */
export function followSystemTheme(): () => void {
  const query = window.matchMedia?.(DARK_QUERY);
  if (!query) return () => undefined;
  const onSystemChange = () => applyThemePreference("system");
  query.addEventListener("change", onSystemChange);
  return () => query.removeEventListener("change", onSystemChange);
}

/** Inlined in <head>: sets `.dark` before the first paint, so there is no flash of the wrong theme. */
export const themeInitScript = `(function(){var t=null;try{t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY
)})}catch(e){}var d=t==="dark"||(t!=="light"&&!!window.matchMedia&&window.matchMedia(${JSON.stringify(
  DARK_QUERY
)}).matches);document.documentElement.classList.toggle("dark",d)})()`;
