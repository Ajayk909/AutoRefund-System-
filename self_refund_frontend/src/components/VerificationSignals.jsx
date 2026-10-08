// Shows the checks the Core API made on a return (barcode, weight, photo,
// AI photo check) so an employee can see why it was sent to review or
// declined by the kiosk.
// Staff screens only: customers never see these details.
import "./VerificationSignals.css";

// signal_type from the API -> the name staff see.
const CHECK_NAMES = {
  barcode: "Barcode",
  weight: "Weight",
  photo: "Photo",
  ai: "AI photo check",
};

// The Core API saves source "none" when no AI verifier is set up. That row is
// not a real check, so we grey it out instead of showing an amber
// "uncertain", which would look like an AI had doubts about the item.
function isNoAiRow(signal) {
  return signal.signal_type === "ai" && signal.source === "none";
}

// match = green, mismatch = red, uncertain = amber (colours in the CSS file).
// The word is always shown too, so the badge doesn't rely on colour alone.
function ResultBadge({ result }) {
  return <span className={`vs-badge vs-badge-${result}`}>{result}</span>;
}

function NoAiRow() {
  return (
    <li className="vs-row vs-row-off">
      <span className="vs-name">{CHECK_NAMES.ai}</span>
      <span className="vs-badge">off</span>
      <span className="vs-reason">No AI configured (not counted)</span>
    </li>
  );
}

function SignalRow({ signal }) {
  if (isNoAiRow(signal)) return <NoAiRow />;

  const name = CHECK_NAMES[signal.signal_type] || signal.signal_type;
  // Only the AI gives a confidence. Rule checks (weight, photo...) leave it
  // empty on purpose, so we never show a made-up number for them.
  const showConfidence = signal.signal_type === "ai" && typeof signal.confidence === "number";
  return (
    <li className="vs-row">
      <span className="vs-name">{name}</span>
      <ResultBadge result={signal.result} />
      <span className="vs-reason">
        {signal.reason}
        {showConfidence && (
          <span className="vs-confidence"> · {Math.round(signal.confidence * 100)}% confident</span>
        )}
      </span>
    </li>
  );
}

export default function VerificationSignals({ signals }) {
  // Returns made before checks were saved (before Phase 4) have no rows.
  const hasSignals = Array.isArray(signals) && signals.length > 0;
  return (
    <div className="vs-box">
      <div className="vs-title">Checks</div>
      {hasSignals ? (
        <ul className="vs-list">
          {signals.map((signal) => <SignalRow key={signal.signal_type} signal={signal} />)}
        </ul>
      ) : (
        <p className="vs-empty">No checks were saved for this return (it was made before checks were recorded).</p>
      )}
    </div>
  );
}
