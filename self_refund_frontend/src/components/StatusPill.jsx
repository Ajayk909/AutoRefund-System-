// A small tinted chip with the status word only (no dot).
// tone: "success" | "review" | "decline" | "primary" | "neutral"
export default function StatusPill({ tone, children }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}
