import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import KioskLayout from "../../components/KioskLayout";
import { ItemSummary } from "../../components/ItemSummary";
import { AlertIcon, CameraIcon, InfoIcon } from "../../components/Icons";
import agent, { AGENT_ORIGIN, agentErrorMessage } from "../../services/agent";
import { money } from "../../services/format";

const newAttemptKey = () => (crypto.randomUUID ? crypto.randomUUID() : `k${Date.now()}${Math.random().toString(16).slice(2)}`);

// Dark panel on the right: the live camera picture, or the photo just taken.
function CameraPanel({ imageUrl, error, onImageError }) {
  return (
    <div className="k-camera">
      <div className="k-camera-empty">
        <CameraIcon size={57} stroke={2} />
        <div className="k-camera-title">Live camera</div>
        <div className="k-camera-sub">{error ? "Camera unavailable. Please try again." : "Live view of the scale"}</div>
      </div>
      {!error && <img src={imageUrl} alt="Live camera view of the scale" className="k-camera-img" onError={onImageError} />}
    </div>
  );
}

function WeightVerificationPage() {
  const [item, setItem] = useState(null);
  const [transaction, setTransaction] = useState(null);
  const [weight, setWeight] = useState(0);
  const [stable, setStable] = useState(false);
  const [loading, setLoading] = useState(false);
  const backendBase = AGENT_ORIGIN;
  const [scaleConnected, setScaleConnected] = useState(true);
  const [displayPreviewUrl, setDisplayPreviewUrl] = useState(`${backendBase}/api/camera/stream`);
  const [cameraError, setCameraError] = useState("");
  const [captureId, setCaptureId] = useState("");
  // Message shown after a failed submit: { kind: "again" | "error", text }
  const [submitMessage, setSubmitMessage] = useState(null);
  // One key per return attempt: a retry after a network error reuses it, so
  // the backend returns the same refund instead of creating a second one.
  const attemptKeyRef = useRef(newAttemptKey());
  // True after the backend asked the customer to place the item again once.
  const weightRecheckedRef = useRef(false);
  const navigate = useNavigate();
  const captureInProgressRef = useRef(false);

  useEffect(() => {
    const si = localStorage.getItem("selectedItem");
    const st = localStorage.getItem("transactionData");
    if (si) setItem(JSON.parse(si));
    if (st) setTransaction(JSON.parse(st));
  }, []);

  useEffect(() => {
    setCaptureId(""); setCameraError(""); setDisplayPreviewUrl(`${backendBase}/api/camera/stream`);
    attemptKeyRef.current = newAttemptKey();
    weightRecheckedRef.current = false;
  }, [backendBase, item?.product_id, item?.barcode, transaction?.receipt_number]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await agent.get("/scale/live");
        setWeight(Number(res.data.weight_grams || 0));
        setStable(Boolean(res.data.stable));
        setScaleConnected(true);
      } catch { setWeight(0); setStable(false); setScaleConnected(false); }
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const captureImage = async () => {
    if (captureInProgressRef.current) return null;
    try {
      captureInProgressRef.current = true; setCameraError("");
      const res = await agent.post("/camera/capture");
      const data = res.data;
      if (data.success) {
        setCaptureId(data.capture_id);
        if (data.preview_data_url) setDisplayPreviewUrl(data.preview_data_url);
        return data;
      }
      setCameraError(data.message || "Failed to capture image"); return null;
    } catch (err) { setCameraError(agentErrorMessage(err, "Camera unavailable. Please try again.")); return null; }
    finally { captureInProgressRef.current = false; }
  };

  const handleSubmit = async () => {
    if (!item || !transaction) return;
    if (item.is_refundable === false) { setSubmitMessage({ kind: "error", text: "This item has already been submitted for refund." }); return; }
    try {
      setLoading(true); setSubmitMessage(null);
      let finalCaptureId = captureId;
      if (!finalCaptureId) { const captured = await captureImage(); if (captured?.capture_id) finalCaptureId = captured.capture_id; }
      // The weight shown on screen is for guidance only: the kiosk agent reads
      // the scale itself when the return is submitted.
      const payload = { transaction_id: transaction.transaction_id, item_id: item.item_id, product_id: item.product_id, quantity: 1, capture_id: finalCaptureId || undefined, weight_rechecked: weightRecheckedRef.current };
      const res = await agent.post("/refunds/start", payload, { headers: { "Idempotency-Key": attemptKeyRef.current } });
      if (!res.data?.success) throw new Error(res.data?.message || "Refund request failed");
      localStorage.setItem("refundResult", JSON.stringify(res.data.refund));
      navigate("/customer/result");
    } catch (err) {
      // Keep the same attempt key when the outcome is unknown (agent unreachable,
      // or the returns service unavailable) so a retry can never create a
      // second return. A definite answer (e.g. item already returned) gets a new key.
      const outcomeUnknown = !err?.response || err.response.data?.code === "CORE_UNAVAILABLE";
      if (!outcomeUnknown) attemptKeyRef.current = newAttemptKey();
      const text = agentErrorMessage(err, "We couldn't submit your return right now. Nothing has been refunded. Please try again.");
      if (err?.response?.data?.code === "WEIGHT_CHECK_AGAIN") {
        // The agent used up the photo; take a fresh one of the re-placed item.
        weightRecheckedRef.current = true;
        setCaptureId(""); setDisplayPreviewUrl(`${backendBase}/api/camera/stream`);
        setSubmitMessage({ kind: "again", text });
      } else {
        setSubmitMessage({ kind: "error", text });
      }
    } finally { setLoading(false); }
  };

  const goBack = () => navigate("/customer/items");

  if (!item || !transaction) {
    return (
      <KioskLayout title="Check your item" onBack={goBack} showCancel>
        <h1 className="k-h1">Choose an item first</h1>
        <p className="k-lead">Go back and tap Return this next to the item.</p>
        <button className="k-btn k-btn-primary k-btn-big k-push-down" onClick={goBack}>Choose an item</button>
      </KioskLayout>
    );
  }

  const placeAgain = submitMessage?.kind === "again";
  const alreadySubmitted = item.is_refundable === false;
  const showError = submitMessage?.kind === "error" || alreadySubmitted;
  const weightText = scaleConnected ? `${Math.round(weight)} g` : "--";

  const side = (
    <>
      <CameraPanel imageUrl={displayPreviewUrl} error={cameraError} onImageError={() => setCameraError("Camera unavailable")} />
      <div className="k-card k-card-grow">
        <h2 className="k-card-title k-card-title-small">Your return</h2>
        <ItemSummary name={item.name} receiptNumber={transaction.receipt_number} />
        <dl className="k-facts k-facts-tight">
          <div><dt>Refund</dt><dd>{money(item.price_at_purchase)}</dd></div>
          <div><dt>Refund to</dt><dd>Original payment</dd></div>
        </dl>
      </div>
    </>
  );

  return (
    <KioskLayout title="Check your item" side={side} onBack={goBack} showCancel scaleText={weightText}>
      {placeAgain && (
        <div className="k-banner">
          <InfoIcon size={32} /> Let's check the weight once more
        </div>
      )}
      <h1 className="k-h1">{placeAgain ? "Place the item again" : "Place the item on the scale"}</h1>
      <p className="k-lead k-lead-close">{placeAgain ? submitMessage.text : "Put it in the middle of the scale, then take your hands away."}</p>

      <div className="k-weight">
        <div className="k-weight-label">Weight on the scale</div>
        <div className="k-weight-value">{weightText}</div>
        {!scaleConnected && (
          <div className="k-weight-problem">
            <strong>Scale not responding</strong>
            Make sure the scale is switched on. If this keeps happening, tap I need help.
          </div>
        )}
      </div>

      {showError && (
        <div className="k-error k-error-compact" role="alert">
          <AlertIcon size={40} stroke={2} />
          <div>{alreadySubmitted ? "This item has already been submitted for refund." : submitMessage.text}</div>
        </div>
      )}

      <div className="k-weigh-action">
        {/* The red box takes this line's place, so the panel never needs to scroll */}
        {!showError && <p className="k-photo-note">The kiosk takes a photo when you tap the button.</p>}
        <button
          className="k-btn k-btn-primary k-btn-big"
          onClick={handleSubmit}
          disabled={loading || !stable || alreadySubmitted}
        >
          {loading ? "Checking your item…" : "Check my item"}
        </button>
      </div>
    </KioskLayout>
  );
}

export default WeightVerificationPage;
