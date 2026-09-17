// Staff session kept in sessionStorage (cleared when the browser tab closes).
// The token is only a key: every staff endpoint is authorised by the backend.
const TOKEN_KEY = "autorefund.staffToken";
const STAFF_KEY = "autorefund.staffUser";

export function getStaffToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getStaffUser() {
  try { return JSON.parse(sessionStorage.getItem(STAFF_KEY) || "null"); }
  catch { return null; }
}

export function saveStaffSession(token, staff) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(STAFF_KEY, JSON.stringify(staff));
  localStorage.removeItem("staffUser"); // legacy, pre-Phase 0
}

export function clearStaffSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(STAFF_KEY);
  localStorage.removeItem("staffUser");
}
