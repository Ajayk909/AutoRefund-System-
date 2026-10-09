// Shows the checks the Core API made on a return (barcode, weight, photo,
// AI photo check) so an employee can see why it was sent to review or
// declined by the kiosk.
// Staff screens only: customers never see these details.
import StatusPill from "./StatusPill";

// signal_type from the API -> the name staff see.
const CHECK_NAMES = {
  barcode: "Barcode",
  weight: "Weight",
  photo: "Photo",
  ai: "AI photo check",
};

// result from the API -> pill word and colour. The word is always shown,
// so the pill doesn't rely on colour alone.
const RESULTS = {
  match: { word: "Match", tone: "success" },
  mismatch: { word: "Mismatch", tone: "decline" },
  uncertain: { word: "Uncertain", tone: "review" },
};

// The Core API saves source "none" when no AI verifier is set up. That row is
// not a real check, so we grey it out instead of showing an amber
// "uncertain", which would look like an AI had doubts about the item.
function isNoAiRow(signal) {
  return signal.signal_type === "ai" && signal.source === "none";
}

function NoAiRow() {
  return (
    <li className="s-check s-check-off">
      <span className="s-check-name">{CHECK_NAMES.ai}</span>
      <span><StatusPill tone="neutral">Off</StatusPill></span>
      <span className="s-check-reason">No AI configured (not counted)</span>
    </li>
  );
}

function SignalRow({ signal }) {
  if (isNoAiRow(signal)) return <NoAiRow />;

  const name = CHECK_NAMES[signal.signal_type] || signal.signal_type;
  const result = RESULTS[signal.result] || { word: signal.result, tone: "neutral" };
  // Only the AI gives a confidence. Rule checks (weight, photo...) leave it
  // empty on purpose, so we never show a made-up number for them.
  const showConfidence = signal.signal_type === "ai" && typeof signal.confidence === "number";
  return (
    <li className="s-check">
      <span className="s-check-name">{name}</span>
      <span><StatusPill tone={result.tone}>{result.word}</StatusPill></span>
      <span className="s-check-reason">
        {signal.reason}
        {showConfidence && ` · ${Math.round(signal.confidence * 100)}% confident`}
      </span>
    </li>
  );
}

export default function VerificationSignals({ signals }) {
  // Returns made before checks were saved (before Phase 4) have no rows.
  const hasSignals = Array.isArray(signals) && signals.length > 0;
  return (
    <div className="s-checks">
      <div className="s-checks-title">Checks</div>
      {hasSignals ? (
        <ul>
          {signals.map((signal) => <SignalRow key={signal.signal_type} signal={signal} />)}
        </ul>
      ) : (
        <p className="s-muted">No checks were saved for this return (it was made before checks were recorded).</p>
      )}
    </div>
  );
}
