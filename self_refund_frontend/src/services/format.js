// Shows an amount as dollars with two decimals, e.g. 3.5 -> "$3.50".
export function money(amount) {
  return `$${Number(amount || 0).toFixed(2)}`;
}

// The server sends its dates (refund_date, decided_at, refunded_at,
// return_deadline) in UTC without a "Z" on the end. We add it; otherwise the
// browser reads them as local time and shows the wrong hour (4-5 h off in Toronto).
// Use this for every server date the screens show or compare.
export function parseServerDate(text) {
  if (!text) return null;
  return new Date(/Z|[+-]\d\d:\d\d$/.test(text) ? text : `${text}Z`);
}

export function isToday(date) {
  return Boolean(date) && date.toDateString() === new Date().toDateString();
}

// "7:58 PM"
export function timeOfDay(date) {
  return date ? date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }) : "";
}

// "Oct 8, 7:58 PM"
export function dayAndTime(date) {
  return date ? date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}

// "Oct 8, 2026, 7:58 PM"
export function fullDateTime(date) {
  return date ? date.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
}

// Whole minutes between a date and now, e.g. for "oldest waiting 12 min".
export function minutesSince(date) {
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
}
