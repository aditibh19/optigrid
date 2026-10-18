/**
 * Token storage. Tokens live in localStorage (mirrored in memory so this also
 * works outside a browser, e.g. in the e2e script).
 *
 * Trade-off worth knowing for the viva: localStorage is readable by any script
 * on the page, so an XSS bug would expose the tokens. Production hardening is
 * to keep the refresh token in an httpOnly, SameSite cookie set by the backend.
 */
const KEY = "evoptigrid.tokens";
export const AUTH_EXPIRED_EVENT = "evoptigrid:auth-expired";

export interface StoredTokens { access_token: string; refresh_token: string }

let memory: StoredTokens | null = null;

export function getTokens(): StoredTokens | null {
  if (memory) return memory;
  try {
    const raw = window.localStorage.getItem(KEY);
    memory = raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch { /* no window / storage blocked */ }
  return memory;
}

export function saveTokens(t: StoredTokens) {
  memory = { access_token: t.access_token, refresh_token: t.refresh_token };
  try { window.localStorage.setItem(KEY, JSON.stringify(memory)); } catch { /* storage unavailable */ }
}

export function clearTokens() {
  memory = null;
  try { window.localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

/** Tells the UI the session is over (refresh failed), so it can send the user to the login page. */
export function notifySessionExpired() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
}
