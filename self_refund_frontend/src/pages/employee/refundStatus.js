// The words and pill colours staff see for each refund status, shared by the
// Overview and the Return log so both screens say the same thing.

// A rejection with no reviewer was made by the kiosk itself: we call it
// "Declined" so staff can tell it apart from their own rejections.
export function statusInfo(row) {
  switch (row.decision_status) {
    case "approved": return { word: "Approved", tone: "success" };
    case "pending_review": return { word: "Waiting for review", tone: "review" };
    case "refunded": return { word: "Refunded", tone: "primary" };
    case "rejected": return row.reviewed_by ? { word: "Rejected", tone: "decline" } : { word: "Declined", tone: "decline" };
    default: return { word: row.decision_status, tone: "neutral" };
  }
}

// Who made the decision: the staff member, or the kiosk when nobody reviewed it.
export function decidedBy(row) {
  if (row.decision_status === "pending_review") return "—";
  return row.reviewed_by || "Kiosk (automatic)";
}
