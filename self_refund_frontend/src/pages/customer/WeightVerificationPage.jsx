import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";
import api from "../../services/api";

function KioskShell() {
  const [time, setTime] = useState(new Date());
  const particles = useMemo(() => Array.from({ length: 16 }, (_, i) => ({ id: i, left: `${4 + Math.random() * 92}%`, bottom: `${Math.random() * 12}%`, size: `${2 + Math.random() * 3}px`, duration: `${10 + Math.random() * 12}s`, delay: `${Math.random() * 8}s` })), []);
  useEffect(() => { const t = setInterval(() => setTime(new Date()), 1000); return () => clearInterval(t); }, []);
  return (
    <>
      <div className="kiosk-particles" aria-hidden>{particles.map((p) => (<span key={p.id} style={{ left: p.left, bottom: p.bottom, width: p.size, height: p.size, "--dur": p.duration, "--delay": p.delay }} />))}</div>
      <div className="kiosk-topbar">
        <div className="topbar-brand"><span className="topbar-dot" />AutoRefund</div>
        <div className="topbar-time">{time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
        <div className="topbar-status">● CUSTOMER MODE</div>
      </div>
    </>
  );
}

function WeightVerificationPage() {
  const [item, setItem] = useState(null);
  const [transaction, setTransaction] = useState(null);
  const [weight, setWeight] = useState(0);
  const [stable, setStable] = useState(false);
  const [loading, setLoading] = useState(false);
  const backendHost = window.location.hostname || "localhost";
  const backendBase = `http://${backendHost}:5000`;
  const [displayPreviewUrl, setDisplayPreviewUrl] = useState(`${backendBase}/api/camera/stream`);
  const [cameraLoading, setCameraLoading] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [capturedImagePath, setCapturedImagePath] = useState("");
  const [capturedImageName, setCapturedImageName] = useState("");
  const navigate = useNavigate();
  const captureInProgressRef = useRef(false);

  useEffect(() => {
    const si = localStorage.getItem("selectedItem");
    const st = localStorage.getItem("transactionData");
    if (si) setItem(JSON.parse(si));
    if (st) setTransaction(JSON.parse(st));
  }, []);

  useEffect(() => {
    setCapturedImagePath(""); setCapturedImageName(""); setCameraError(""); setDisplayPreviewUrl(`${backendBase}/api/camera/stream`);
  }, [backendBase, item?.product_id, item?.barcode, transaction?.receipt_number]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const res = await api.get("/scale/live");
        setWeight(Number(res.data.weight_grams || 0));
        setStable(Boolean(res.data.stable));
      } catch { setWeight(0); setStable(false); }
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const captureImage = async () => {
    if (captureInProgressRef.current) return null;
    try {
      captureInProgressRef.current = true; setCameraLoading(true); setCameraError("");
      const res = await api.post("/camera/capture");
      const data = res.data;
      if (data.success) {
        const backendImagePath = data.image_path || "";
        const backendImageUrl = data.image_url || "";
        const fileName = data.file_name || backendImagePath.split("/").pop() || "captured-image.jpg";
        setCapturedImagePath(backendImagePath); setCapturedImageName(fileName);
        if (backendImageUrl) setDisplayPreviewUrl(`${backendBase}${backendImageUrl}?ts=${Date.now()}`);
        return data;
      }
      setCameraError(data.message || "Failed to capture image"); return null;
    } catch { setCameraError("Failed to capture image from camera"); return null; }
    finally { captureInProgressRef.current = false; setCameraLoading(false); }
  };

  const handleSubmit = async () => {
    if (!item || !transaction) return;
    if (item.is_refundable === false) { alert("This item has already been submitted for refund."); navigate("/customer/items"); return; }
    try {
      setLoading(true);
      let finalImagePath = capturedImagePath;
      if (!finalImagePath) { const captured = await captureImage(); if (captured?.image_path) finalImagePath = captured.image_path; }
      const payload = { transaction_id: transaction.transaction_id, item_id: item.item_id, product_id: item.product_id, measured_weight_grams: Number(weight), image_path: finalImagePath || "mock_images/test.jpg", kiosk_id: "KIOSK-001" };
      const res = await api.post("/refunds/start", payload);
      if (!res.data?.success) throw new Error(res.data?.message || "Refund request failed");
      localStorage.setItem("refundResult", JSON.stringify(res.data.refund));
      navigate("/customer/result");
    } catch (err) {
      alert(err?.response?.data?.message || err?.response?.data?.error || err?.message || "Failed to process refund. Please try again.");
    } finally { setLoading(false); }
  };

  if (!item || !transaction) {
    return (
      <PageWrapper><KioskShell />
        <Layout title="Weight Verification" subtitle="No item selected.">
          <div style={{ display: "flex", flexDirection: "column", gap: 14, alignItems: "flex-start", padding: "40px 0" }}>
            <button className="ghost-btn" onClick={() => navigate("/customer/items")}>← Select an Item</button>
            <button className="ghost-btn" onClick={() => navigate("/")}>🏠 Back to Home</button>
          </div>
        </Layout>
      </PageWrapper>
    );
  }

  const diff = Number(weight) - Number(item.expected_weight_grams || 0);
  const tolerance = Number(item.expected_weight_grams || 0) * (Number(item.weight_tolerance_percent || 10) / 100);
  const ok = Math.abs(diff) <= tolerance;
  const progress = item.expected_weight_grams > 0 ? Math.min((weight / item.expected_weight_grams) * 100, 115) : 0;
  const progressCapped = Math.min(progress, 100);
  const ringColor = !stable ? "#38bdf8" : ok ? "#10fbc4" : "#fbbf24";
  const stageLabel = !stable ? "Measuring…" : ok ? "✓ Weight verified" : "⚠ Weight differs";
  const stageDesc = !stable ? "Keep the item still on the scale pad." : ok ? "This item matches the expected weight. Ready to submit!" : `This item differs by ${Math.abs(diff).toFixed(1)} g from the expected weight. Your refund may need manual review.`;

  return (
    <PageWrapper>
      <KioskShell />
      <Layout title="" subtitle="">
        <div className="kiosk-content wv2-page">
          {/* Progress */}
          <div className="wv2-progress">
            {["Receipt", "Item", "Weigh", "Done!"].map((s, i) => (
              <div key={s} className="wv2-progress-part">
                <div className={`wv2-step ${i < 2 ? "wv2-done" : i === 2 ? "wv2-active" : ""}`}>
                  <div className="wv2-step-circle">{i < 2 ? "✓" : i === 3 ? "🎁" : i + 1}</div>
                  <div className="wv2-step-label">{s}</div>
                </div>
                {i < 3 && <div className={`wv2-progress-line ${i < 2 ? "wv2-line-done" : ""}`} />}
              </div>
            ))}
          </div>

          {/* Item banner */}
          <div className="wv2-item-banner">
            <div className="wv2-item-icon">📦</div>
            <div className="wv2-item-info">
              <div className="wv2-item-name">{item.name}</div>
              <div className="wv2-item-meta">Barcode {item.barcode} · Receipt {transaction.receipt_number} · Expected: {item.expected_weight_grams} g</div>
              {item.is_refundable === false && (
                <div className="wv2-locked-note">{item.refund_status ? `Already submitted (${item.refund_status})` : "Already submitted for refund"}</div>
              )}
            </div>
            <div className="wv2-item-actions">
              <button className="ghost-btn" onClick={() => navigate("/customer/items")}>Change item</button>
              <button className="ghost-btn" onClick={() => navigate("/")}>🏠 Home</button>
            </div>
          </div>

          <div className="wv2-main">
            {/* Scale section */}
            <section className="wv2-scale-section">
              <div className="wv2-scale-card" style={{ "--ring": ringColor }}>
                <div className="wv2-ring-outer">
                  <div className="wv2-ring-inner" style={{ borderColor: `${ringColor}50`, boxShadow: `0 0 70px ${ringColor}28` }}>
                    <div className="wv2-ring-core">
                      <div className="wv2-weight-val" style={{ color: ringColor }}>{weight}</div>
                      <div className="wv2-weight-unit">grams</div>
                      <div className="wv2-weight-status" style={{ color: ringColor }}>{stable ? (ok ? "✓ OK" : "⚠ Check") : "⟳"}</div>
                    </div>
                    {stable && <div className="wv2-ring-pulse" style={{ background: `${ringColor}10`, boxShadow: `0 0 0 14px ${ringColor}07, 0 0 0 28px ${ringColor}03` }} />}
                  </div>
                </div>
                <div className="wv2-stage" style={{ borderColor: `${ringColor}25`, background: `${ringColor}08` }}>
                  <div className="wv2-stage-label" style={{ color: ringColor }}>{stageLabel}</div>
                  <p className="wv2-stage-desc">{stageDesc}</p>
                </div>
                <div className="wv2-gauge-section">
                  <div className="wv2-gauge-labels-top">
                    <span>0 g</span>
                    <span style={{ color: ringColor }}>Expected: {item.expected_weight_grams} g</span>
                  </div>
                  <div className="wv2-gauge-track">
                    <div className="wv2-gauge-fill" style={{ width: `${progressCapped}%`, background: ok ? "linear-gradient(90deg,#059669,#10fbc4)" : weight > 0 ? "linear-gradient(90deg,#d97706,#fbbf24)" : "linear-gradient(90deg,#38bdf8,#60a5fa)" }} />
                    <div className="wv2-gauge-target" />
                  </div>
                  <div className="wv2-gauge-labels-bot">
                    <span style={{ color: "#6882a8" }}>{stable ? ok ? `Within ±${tolerance.toFixed(0)} g tolerance` : `Difference: ${diff > 0 ? "+" : ""}${diff.toFixed(1)} g` : "Waiting for stable reading…"}</span>
                    <span style={{ color: "#6882a8" }}>{progressCapped.toFixed(0)}%</span>
                  </div>
                </div>
                <div className="wv2-metrics">
                  {[{ label: "Expected", val: `${item.expected_weight_grams} g`, color: null }, { label: "Measured", val: `${weight} g`, color: ringColor }, { label: "Tolerance", val: `±${tolerance.toFixed(1)} g`, color: null }, { label: "Scale", val: stable ? "Stable" : "Reading", color: stable ? "#10fbc4" : "#fbbf24" }].map((m) => (
                    <div key={m.label} className="wv2-metric">
                      <span>{m.label}</span>
                      <strong style={m.color ? { color: m.color } : {}}>{m.val}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            {/* Side */}
            <section className="wv2-side">
              <div className="wv2-instructions-card">
                <div className="wv2-inst-title">How to weigh your item</div>
                {[
                  { step: "1", icon: "📦", text: "Place only this item on the scale.", done: weight > 10 },
                  { step: "2", icon: "🤚", text: "Hold still — don't touch the scale.", done: stable },
                  { step: "3", icon: "📸", text: "Click Capture Now to take a photo.", done: !!capturedImageName },
                  { step: "4", icon: "✅", text: "Submit the refund request.", done: stable && !!capturedImageName },
                ].map((inst) => (
                  <div key={inst.step} className={`wv2-inst ${inst.done ? "wv2-inst-done" : ""}`}>
                    <div className="wv2-inst-icon">{inst.done ? "✓" : inst.icon}</div>
                    <div className="wv2-inst-text">{inst.text}</div>
                  </div>
                ))}
              </div>

              <div className="wv2-camera-card">
                <div className="wv2-camera-top">
                  <div className="wv2-camera-label">Camera Preview</div>
                  <button className="wv2-camera-btn" type="button" onClick={() => captureImage()} disabled={cameraLoading || !!capturedImagePath}>
                    {cameraLoading ? "Capturing..." : capturedImagePath ? "Captured ✓" : "Capture Now"}
                  </button>
                </div>
                <div className="wv2-camera-frame">
                  <div className="wv2-camera-corner wv2-cc-tl" /><div className="wv2-camera-corner wv2-cc-tr" />
                  <div className="wv2-camera-corner wv2-cc-bl" /><div className="wv2-camera-corner wv2-cc-br" />
                  <img src={displayPreviewUrl} alt="Camera preview" className="wv2-camera-img" onError={() => setCameraError("Live camera stream not available")} />
                  {!capturedImagePath && <div className="wv2-camera-scan" />}
                </div>
                <div className="wv2-camera-status">
                  <span className={`wv2-camera-dot ${cameraError ? "wv2-camera-dot-error" : capturedImageName ? "wv2-camera-dot-ok" : ""}`} />
                  {cameraError ? cameraError : capturedImageName ? `Captured: ${capturedImageName}` : stable ? "Weight stable. Click Capture Now." : "Waiting for stable reading"}
                </div>
                {capturedImageName && (
                  <div className="wv2-camera-captured-box">
                    <div className="wv2-camera-captured-title">Last captured image</div>
                    <div className="wv2-camera-captured-name">{capturedImageName}</div>
                  </div>
                )}
              </div>

              <button
                className={`wv2-submit ${stable && !loading && item.is_refundable !== false ? "wv2-submit-ready" : ""}`}
                onClick={handleSubmit}
                disabled={loading || !stable || item.is_refundable === false}
              >
                {item.is_refundable === false ? <><span className="wv2-submit-icon">⛔</span> Item Already Refunded</>
                  : loading ? <><span className="wv2-spinner" /> Processing your refund…</>
                  : stable ? <><span className="wv2-submit-icon">🚀</span> Submit Refund Request →</>
                  : <><span className="wv2-submit-icon">⚖️</span> Waiting for stable reading…</>}
              </button>

              <button className="ghost-btn" style={{ width: "100%" }} onClick={() => navigate("/customer/items")}>
                ← Back to Item Selection
              </button>
            </section>
          </div>
        </div>
      </Layout>

      <style>{`
        @keyframes wv2Up{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
        @keyframes wv2Pulse{0%,100%{transform:scale(1);opacity:.6}50%{transform:scale(1.1);opacity:1}}
        @keyframes wv2Scan{0%{top:10%;opacity:0}10%{opacity:.9}90%{opacity:.3}100%{top:88%;opacity:0}}
        @keyframes wv2Spin{to{transform:rotate(360deg)}}
        .wv2-page{min-height:calc(100vh - 110px);display:flex;flex-direction:column;gap:20px}
        .wv2-progress{display:flex;align-items:center;padding:18px 28px;border-radius:16px;background:rgba(4,10,22,.75);border:1px solid rgba(56,189,248,.1);animation:wv2Up .4s ease both;gap:0}
        .wv2-progress-part{display:flex;align-items:center;flex:1}
        .wv2-step{display:flex;flex-direction:column;align-items:center;gap:7px}
        .wv2-step-circle{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;background:rgba(56,189,248,.08);color:#3d5270;border:1px solid rgba(56,189,248,.14)}
        .wv2-done .wv2-step-circle{background:rgba(16,251,196,.14);color:#10fbc4;border-color:rgba(16,251,196,.3)}
        .wv2-active .wv2-step-circle{background:linear-gradient(135deg,#0ea5e9,#38bdf8);color:#020810;box-shadow:0 0 20px rgba(56,189,248,.5);border:none}
        .wv2-step-label{font-size:11px;color:#3d5270;font-family:'Space Mono',monospace;letter-spacing:.07em;white-space:nowrap}
        .wv2-done .wv2-step-label{color:#10fbc4}
        .wv2-active .wv2-step-label{color:#38bdf8}
        .wv2-progress-line{flex:1;height:2px;background:rgba(56,189,248,.07);margin:0 6px}
        .wv2-line-done{background:linear-gradient(90deg,rgba(16,251,196,.35),rgba(16,251,196,.1))}
        .wv2-item-banner{display:flex;align-items:center;gap:16px;padding:18px 22px;border-radius:18px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.14);animation:wv2Up .45s ease both .08s}
        .wv2-item-icon{font-size:28px;flex-shrink:0}
        .wv2-item-info{flex:1}
        .wv2-item-name{font-size:18px;font-weight:800;color:#fff}
        .wv2-item-meta{font-size:12px;color:#6882a8;font-family:'Space Mono',monospace;margin-top:4px}
        .wv2-locked-note{margin-top:10px;display:inline-flex;width:fit-content;padding:6px 10px;border-radius:999px;font-size:11px;font-weight:700;color:#fbbf24;background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.22)}
        .wv2-item-actions{flex-shrink:0;display:flex;gap:8px;flex-wrap:wrap}
        .wv2-main{display:grid;grid-template-columns:1.1fr .9fr;gap:20px;flex:1;animation:wv2Up .5s ease both .14s}
        .wv2-scale-card{padding:28px;border-radius:24px;height:100%;background:rgba(8,16,36,.95);border:1px solid rgba(56,189,248,.14);display:flex;flex-direction:column;gap:20px;box-shadow:0 0 40px rgba(56,189,248,.06)}
        .wv2-ring-outer{display:flex;justify-content:center;padding:10px 0}
        .wv2-ring-inner{width:230px;height:230px;border-radius:50%;border:2px solid;position:relative;display:flex;align-items:center;justify-content:center;transition:border-color .5s ease,box-shadow .5s ease;background:radial-gradient(circle,rgba(4,10,22,.92),rgba(8,16,36,.8))}
        .wv2-ring-core{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;position:relative;z-index:2}
        .wv2-weight-val{font-family:'Orbitron',sans-serif;font-size:54px;font-weight:900;line-height:1;transition:color .5s ease}
        .wv2-weight-unit{font-family:'Space Mono',monospace;font-size:12px;letter-spacing:.12em;color:#6882a8;text-transform:uppercase}
        .wv2-weight-status{font-size:14px;font-weight:700;margin-top:4px;transition:color .5s ease}
        .wv2-ring-pulse{position:absolute;inset:-20px;border-radius:50%;animation:wv2Pulse 2.2s ease-in-out infinite;pointer-events:none;z-index:0}
        .wv2-stage{padding:18px 22px;border-radius:18px;border:1px solid;text-align:center;transition:all .4s ease}
        .wv2-stage-label{font-size:18px;font-weight:800;margin-bottom:8px;transition:color .4s ease}
        .wv2-stage-desc{font-size:14px;color:#9db0ce;line-height:1.65}
        .wv2-gauge-section{display:flex;flex-direction:column;gap:8px}
        .wv2-gauge-labels-top,.wv2-gauge-labels-bot{display:flex;justify-content:space-between;font-size:11px;color:#6882a8;font-family:'Space Mono',monospace}
        .wv2-gauge-track{position:relative;height:12px;border-radius:999px;background:rgba(255,255,255,.06);overflow:visible}
        .wv2-gauge-fill{height:100%;border-radius:999px;transition:width .8s cubic-bezier(.34,1.56,.64,1)}
        .wv2-gauge-target{position:absolute;right:0;top:-4px;width:3px;height:20px;background:#8ddcff;border-radius:2px}
        .wv2-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
        .wv2-metric{padding:14px 12px;border-radius:14px;text-align:center;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07)}
        .wv2-metric span{display:block;color:#6882a8;font-size:9px;letter-spacing:.12em;text-transform:uppercase;font-family:'Space Mono',monospace;margin-bottom:7px}
        .wv2-metric strong{color:#fff;font-size:15px}
        .wv2-side{display:flex;flex-direction:column;gap:14px}
        .wv2-instructions-card{padding:22px;border-radius:20px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);display:flex;flex-direction:column;gap:12px}
        .wv2-inst-title{font-size:14px;font-weight:800;color:#fff;letter-spacing:.02em}
        .wv2-inst{display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:14px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);transition:all .3s ease}
        .wv2-inst-done{background:rgba(16,251,196,.07);border-color:rgba(16,251,196,.25)}
        .wv2-inst-icon{width:36px;height:36px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:16px;background:rgba(56,189,248,.09);border:1px solid rgba(56,189,248,.16)}
        .wv2-inst-done .wv2-inst-icon{background:rgba(16,251,196,.14);border-color:rgba(16,251,196,.3);color:#10fbc4;font-weight:900}
        .wv2-inst-text{font-size:14px;color:#a8c0d8;line-height:1.5}
        .wv2-inst-done .wv2-inst-text{color:#10fbc4}
        .wv2-camera-card{padding:18px;border-radius:20px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);display:flex;flex-direction:column;gap:12px}
        .wv2-camera-top{display:flex;justify-content:space-between;align-items:center;gap:12px}
        .wv2-camera-label{font-size:11px;color:#6882a8;font-family:'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase}
        .wv2-camera-btn{padding:9px 14px;border-radius:10px;border:1px solid rgba(56,189,248,.2);background:rgba(56,189,248,.1);color:#d8ecff;font-size:12px;font-weight:700;cursor:pointer;transition:all .25s ease}
        .wv2-camera-btn:hover{transform:translateY(-1px);background:rgba(56,189,248,.18)}
        .wv2-camera-btn:disabled{opacity:.6;cursor:not-allowed;transform:none}
        .wv2-camera-frame{position:relative;height:220px;border-radius:14px;background:linear-gradient(180deg,rgba(4,10,22,.92),rgba(8,16,36,.78));border:1px dashed rgba(56,189,248,.2);overflow:hidden;display:flex;align-items:center;justify-content:center}
        .wv2-camera-img{width:100%;height:100%;object-fit:cover;display:block}
        .wv2-camera-corner{position:absolute;width:20px;height:20px;border-color:rgba(16,251,196,.55);border-style:solid;z-index:3}
        .wv2-cc-tl{top:10px;left:10px;border-width:2px 0 0 2px}
        .wv2-cc-tr{top:10px;right:10px;border-width:2px 2px 0 0}
        .wv2-cc-bl{bottom:10px;left:10px;border-width:0 0 2px 2px}
        .wv2-cc-br{bottom:10px;right:10px;border-width:0 2px 2px 0}
        .wv2-camera-scan{position:absolute;left:14%;right:14%;height:1.5px;background:linear-gradient(90deg,transparent,rgba(56,189,248,.9),transparent);box-shadow:0 0 12px rgba(56,189,248,.6);animation:wv2Scan 3s ease-in-out infinite;z-index:2}
        .wv2-camera-status{display:flex;align-items:center;gap:8px;font-size:12px;color:#9ab2cf;min-height:20px;word-break:break-word}
        .wv2-camera-dot{width:6px;height:6px;border-radius:50%;background:#fbbf24;box-shadow:0 0 7px #fbbf24;animation:wv2Pulse 1.5s ease-in-out infinite;flex-shrink:0}
        .wv2-camera-dot-ok{background:#10fbc4;box-shadow:0 0 7px #10fbc4}
        .wv2-camera-dot-error{background:#fb7185;box-shadow:0 0 7px #fb7185}
        .wv2-camera-captured-box{padding:12px 14px;border-radius:12px;background:rgba(16,251,196,.07);border:1px solid rgba(16,251,196,.2)}
        .wv2-camera-captured-title{font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:#6fe9d0;font-family:'Space Mono',monospace;margin-bottom:6px}
        .wv2-camera-captured-name{font-size:13px;color:#e8fffb;word-break:break-all}
        .wv2-submit{width:100%;padding:20px 24px;border-radius:16px;border:2px solid rgba(56,189,248,.18);font-size:16px;font-weight:700;cursor:pointer;font-family:'DM Sans',sans-serif;display:flex;align-items:center;justify-content:center;gap:12px;background:rgba(56,189,248,.07);color:#6882a8;transition:all .3s ease}
        .wv2-submit:disabled{opacity:.8;cursor:not-allowed}
        .wv2-submit-ready{background:linear-gradient(135deg,#059669,#10fbc4);color:#020810;border-color:transparent;box-shadow:0 8px 36px rgba(16,251,196,.5);font-size:17px}
        .wv2-submit-ready:hover{transform:translateY(-3px);box-shadow:0 18px 52px rgba(16,251,196,.65)}
        .wv2-submit-icon{font-size:20px}
        .wv2-spinner{width:18px;height:18px;border-radius:50%;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;animation:wv2Spin .7s linear infinite}
        @media(max-width:980px){.wv2-main{grid-template-columns:1fr}.wv2-metrics{grid-template-columns:repeat(2,1fr)}}
        @media(max-width:600px){.wv2-item-banner{flex-wrap:wrap}.wv2-ring-inner{width:185px;height:185px}.wv2-weight-val{font-size:44px}.wv2-item-actions{flex-direction:column}}
      `}</style>
    </PageWrapper>
  );
}

export default WeightVerificationPage;