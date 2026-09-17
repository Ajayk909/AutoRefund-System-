import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";
import api from "../../services/api";
import useBarcodeScanner from "../../hooks/useBarcodeScanner";

function KioskShell({ mode = "Customer" }) {
  const [time, setTime] = useState(new Date());
  const particles = useMemo(() => Array.from({ length: 16 }, (_, i) => ({
    id: i, left: `${4 + Math.random() * 92}%`, bottom: `${Math.random() * 12}%`,
    size: `${2 + Math.random() * 3}px`, duration: `${10 + Math.random() * 12}s`, delay: `${Math.random() * 8}s`,
  })), []);
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <>
      <div className="kiosk-particles" aria-hidden>
        {particles.map((p) => (
          <span key={p.id} style={{ left: p.left, bottom: p.bottom, width: p.size, height: p.size, "--dur": p.duration, "--delay": p.delay }} />
        ))}
      </div>
      <div className="kiosk-topbar">
        <div className="topbar-brand"><span className="topbar-dot" />AutoRefund</div>
        <div className="topbar-time">{time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
        <div className="topbar-status">● {mode.toUpperCase()} MODE</div>
      </div>
    </>
  );
}

function ReceiptScanPage() {
  const [receiptNumber, setReceiptNumber] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [inputFocused, setInputFocused] = useState(false);
  const [scanning, setScanning] = useState(true);
  const [scanMessage, setScanMessage] = useState("Point the receipt barcode at the camera");
  const navigate = useNavigate();

  const handleContinue = async (manualReceiptNumber) => {
    const value = (manualReceiptNumber ?? receiptNumber).trim();
    if (!value) { setError("Please enter your receipt number first."); return; }
    try {
      setLoading(true); setError("");
      const response = await api.get(`/transactions/${value}`);
      localStorage.setItem("transactionData", JSON.stringify(response.data.transaction));
      navigate("/customer/items");
    } catch (err) {
      // 404 = unknown receipt. Other errors (e.g. this kiosk isn't set up)
      // carry a customer-safe message from the server.
      setError(err?.response?.status === 404 || !err?.response?.data?.message
        ? "We couldn't find that receipt. Please check the number and try again."
        : err.response.data.message);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!scanning) return;
    const interval = setInterval(async () => {
      try {
        const res = await api.get("/receipt/scan");
        if (res.data?.success && res.data?.found && res.data?.barcode) {
          const scannedReceipt = String(res.data.barcode).trim();
          setReceiptNumber(scannedReceipt);
          setScanMessage(`Receipt detected: ${scannedReceipt}`);
          setScanning(false);
          await handleContinue(scannedReceipt);
        } else { setScanMessage("Scanning receipt barcode..."); }
      } catch { setScanMessage("Scanner is waiting for a barcode..."); }
    }, 1000);
    return () => clearInterval(interval);
  }, [scanning]);

  // USB barcode scanner (HID keyboard mode) - works even without input focus
  useBarcodeScanner((code) => {
    if (loading) return;
    setReceiptNumber(code);
    setError("");
    setScanMessage(`Receipt detected: ${code}`);
    handleContinue(code);
  });

  const hasInput = receiptNumber.trim().length > 0;

  return (
    <PageWrapper>
      <KioskShell mode="Customer" />
      <Layout title="" subtitle="">
        <div className="kiosk-content rsp-page">

          {/* Progress bar */}
          <div className="rsp-progress-bar">
            {["Receipt", "Select Item", "Weigh", "Done!"].map((label, i) => (
              <div key={label} className="rsp-progress-part">
                <div className={`rsp-progress-step ${i === 0 ? "rsp-active" : ""}`}>
                  <div className={`rsp-step-circle ${i > 0 ? "rsp-inactive" : ""}`}>
                    {i === 0 ? "1" : i === 1 ? "2" : i === 2 ? "3" : "✓"}
                  </div>
                  <div className={`rsp-step-label ${i > 0 ? "rsp-label-dim" : ""}`}>{label}</div>
                </div>
                {i < 3 && <div className="rsp-progress-line" />}
              </div>
            ))}
          </div>

          <div className="rsp-main">
            {/* Left: scanner visual */}
            <section className="rsp-left">
              <div className="rsp-eyebrow">Step 1 of 3</div>
              <h1 className="rsp-title">Scan or enter your receipt</h1>
              <p className="rsp-subtitle">
                Scan the receipt barcode with the handheld scanner or hold it in front of the camera, or type the receipt number on the right.
              </p>

              {/* Barcode Scanner Animation */}
              <div className="rsp-scanner-card">
                <div className="rsp-scanner-top">
                  <div className="rsp-scanner-label">Barcode Scanner</div>
                  <button className="rsp-scan-toggle" type="button" onClick={() => {
                    setScanning(prev => !prev);
                    setScanMessage(scanning ? "Scanner paused. You can type manually." : "Point the receipt barcode at the camera");
                  }}>
                    {scanning ? "Pause Scan" : "Resume Scan"}
                  </button>
                </div>

                <div className="rsp-scanner-viewport">
                  {/* Corner brackets */}
                  <div className="rsp-corner rsp-corner-tl" />
                  <div className="rsp-corner rsp-corner-tr" />
                  <div className="rsp-corner rsp-corner-bl" />
                  <div className="rsp-corner rsp-corner-br" />

                  {/* Simulated barcode lines */}
                  <div className="rsp-barcode-sim">
                    {[3,7,4,9,2,6,5,8,3,7,4,6,9,2,5,8,3,7,4,6,9,2,5].map((w, i) => (
                      <div key={i} className="rsp-bar-line" style={{ width: `${w * 1.5}px`, opacity: scanning ? 1 : 0.3 }} />
                    ))}
                  </div>

                  {/* Laser scan line */}
                  {scanning && <div className="rsp-laser" />}

                  {/* Status overlay */}
                  <div className="rsp-scan-overlay">
                    <div className={`rsp-scan-status-dot ${scanning ? "rsp-dot-active" : "rsp-dot-paused"}`} />
                    <span>{scanMessage}</span>
                  </div>
                </div>

                <div className="rsp-scanner-footer">
                  <div className={`rsp-scanner-dot ${scanning ? "rsp-scanner-dot-on" : "rsp-scanner-dot-off"}`} />
                  <span>{scanning ? "Scanner active — awaiting barcode" : "Scanner paused"}</span>
                </div>
              </div>

              <div className="rsp-tips">
                {[
                  { icon: "📋", text: "Find the receipt number at the top or bottom of your paper receipt" },
                  { icon: "📷", text: "Aim the handheld scanner at the barcode, or hold it flat and steady in front of the camera" },
                  { icon: "💬", text: "Manual entry on the right always works if scanning doesn't" },
                ].map((tip, i) => (
                  <div key={i} className="rsp-tip">
                    <div className="rsp-tip-icon">{tip.icon}</div>
                    <div className="rsp-tip-text">{tip.text}</div>
                  </div>
                ))}
              </div>
            </section>

            {/* Right: manual entry */}
            <section className="rsp-right">
              <div className="rsp-card">
                <div className="rsp-card-header">
                  <div className="rsp-card-icon">🧾</div>
                  <div>
                    <div className="rsp-card-badge">Receipt Lookup</div>
                    <h2 className="rsp-card-title">Enter your receipt number</h2>
                  </div>
                </div>

                <div className={`rsp-input-wrap ${inputFocused ? "focused" : ""} ${hasInput ? "has-val" : ""} ${error ? "has-err" : ""}`}>
                  <label className="rsp-input-label">Receipt Number</label>
                  <input
                    className="rsp-input" type="text" placeholder="e.g. RCP-1001"
                    value={receiptNumber}
                    onChange={(e) => { setReceiptNumber(e.target.value); setError(""); }}
                    onKeyDown={(e) => e.key === "Enter" && handleContinue()}
                    onFocus={() => setInputFocused(true)}
                    onBlur={() => setInputFocused(false)}
                    autoFocus
                  />
                  {hasInput && (
                    <button className="rsp-input-clear" onClick={() => { setReceiptNumber(""); setError(""); }} aria-label="Clear">✕</button>
                  )}
                </div>

                {error && (
                  <div className="rsp-error">
                    <span className="rsp-error-icon">⚠️</span>
                    <div>
                      <div className="rsp-error-title">Receipt not found</div>
                      <div className="rsp-error-body">{error}</div>
                    </div>
                  </div>
                )}

                <div className="rsp-status-chips">
                  <div className={`rsp-chip ${hasInput ? "rsp-chip-on" : ""}`}>
                    <span className="rsp-chip-dot" />
                    {hasInput ? "Receipt number ready" : "Waiting for input"}
                  </div>
                  <div className={`rsp-chip ${scanning ? "rsp-chip-loading" : ""}`}>
                    <span className="rsp-chip-dot" />
                    {scanning ? "Auto-scanning..." : "Scanner paused"}
                  </div>
                  <div className={`rsp-chip ${loading ? "rsp-chip-loading" : ""}`}>
                    <span className="rsp-chip-dot" />
                    {loading ? "Searching database..." : "Ready to search"}
                  </div>
                </div>

                <button
                  className={`rsp-submit-btn ${hasInput && !loading ? "rsp-submit-ready" : ""}`}
                  onClick={() => handleContinue()}
                  disabled={loading || !hasInput}
                >
                  {loading ? (
                    <><span className="rsp-spinner" />Looking up your receipt...</>
                  ) : (
                    <>{hasInput ? "✓ Find My Receipt" : "Scan or enter a receipt number"}{hasInput && <span className="rsp-btn-arrow">→</span>}</>
                  )}
                </button>

                <div className="rsp-example-hint">
                  <span className="rsp-hint-icon">💡</span>
                  <span>Demo receipt number: <strong className="rsp-example-code">RCP-1001</strong></span>
                </div>

                <button className="ghost-btn" style={{ width: "100%", marginTop: 8 }} onClick={() => navigate("/")}>
                  ← Back to home
                </button>
              </div>
            </section>
          </div>
        </div>
      </Layout>

      <style>{`
        @keyframes rspUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        @keyframes rspSpin{to{transform:rotate(360deg)}}
        @keyframes rspShake{0%{transform:translateX(-8px)}25%{transform:translateX(6px)}50%{transform:translateX(-4px)}75%{transform:translateX(3px)}100%{transform:translateX(0)}}
        @keyframes laserScan{0%{top:8%;opacity:0}10%{opacity:1}90%{opacity:.7}100%{top:88%;opacity:0}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}

        .rsp-page{min-height:calc(100vh - 110px);display:flex;flex-direction:column;gap:28px}
        .rsp-progress-bar{display:flex;align-items:center;padding:20px 32px;background:rgba(4,10,22,.75);border-radius:18px;border:1px solid rgba(56,189,248,.1);animation:rspUp .4s ease both;gap:0}
        .rsp-progress-part{display:flex;align-items:center;flex:1}
        .rsp-progress-step{display:flex;flex-direction:column;align-items:center;gap:8px}
        .rsp-step-circle{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:800;background:linear-gradient(135deg,#0ea5e9,#38bdf8);color:#020810;box-shadow:0 0 20px rgba(56,189,248,.5)}
        .rsp-inactive{background:rgba(56,189,248,.08)!important;color:#6882a8!important;box-shadow:none!important;border:1px solid rgba(56,189,248,.14)!important}
        .rsp-step-label{font-size:11px;color:#38bdf8;font-family:'Space Mono',monospace;letter-spacing:.08em;white-space:nowrap}
        .rsp-label-dim{color:#3d5270!important}
        .rsp-progress-line{flex:1;height:2px;background:linear-gradient(90deg,rgba(56,189,248,.28),rgba(56,189,248,.06));margin:0 6px}
        .rsp-main{display:grid;grid-template-columns:1fr 1fr;gap:32px;flex:1;animation:rspUp .48s ease both .1s}
        .rsp-left{display:flex;flex-direction:column;gap:22px}
        .rsp-eyebrow{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:#38bdf8;opacity:.9}
        .rsp-title{font-family:'Orbitron',sans-serif;font-size:clamp(22px,2.8vw,38px);font-weight:800;color:#fff;line-height:1.15;letter-spacing:-.01em}
        .rsp-subtitle{font-size:15px;color:#8aa4c4;line-height:1.75;max-width:440px}
        .rsp-scanner-card{padding:20px;border-radius:22px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.14);display:flex;flex-direction:column;gap:14px;max-width:480px}
        .rsp-scanner-top{display:flex;justify-content:space-between;align-items:center}
        .rsp-scanner-label{font-size:11px;color:#6882a8;font-family:'Space Mono',monospace;letter-spacing:.12em;text-transform:uppercase}
        .rsp-scan-toggle{padding:9px 16px;border-radius:10px;border:1px solid rgba(56,189,248,.2);background:rgba(56,189,248,.1);color:#d8ecff;font-size:12px;font-weight:700;cursor:pointer;transition:all .25s ease}
        .rsp-scan-toggle:hover{background:rgba(56,189,248,.18);transform:translateY(-1px)}
        .rsp-scanner-viewport{
          position:relative;height:200px;border-radius:14px;
          background:linear-gradient(180deg,rgba(2,6,14,.95),rgba(4,12,28,.9));
          border:1px solid rgba(56,189,248,.2);overflow:hidden;
          display:flex;align-items:center;justify-content:center;
        }
        .rsp-corner{position:absolute;width:22px;height:22px;border-color:rgba(16,251,196,.7);border-style:solid;z-index:3}
        .rsp-corner-tl{top:10px;left:10px;border-width:2px 0 0 2px}
        .rsp-corner-tr{top:10px;right:10px;border-width:2px 2px 0 0}
        .rsp-corner-bl{bottom:10px;left:10px;border-width:0 0 2px 2px}
        .rsp-corner-br{bottom:10px;right:10px;border-width:0 2px 2px 0}
        .rsp-barcode-sim{display:flex;align-items:center;gap:3px;height:100px;padding:0 20px;transition:opacity .4s}
        .rsp-bar-line{height:100%;background:rgba(56,189,248,.7);border-radius:1px;transition:opacity .4s}
        .rsp-laser{position:absolute;left:8%;right:8%;height:2px;background:linear-gradient(90deg,transparent,#ff4d6d,#fbbf24,#ff4d6d,transparent);box-shadow:0 0 12px rgba(255,77,109,.8),0 0 24px rgba(255,77,109,.4);animation:laserScan 2.2s ease-in-out infinite;z-index:4}
        .rsp-scan-overlay{position:absolute;bottom:12px;left:0;right:0;display:flex;align-items:center;justify-content:center;gap:8px;z-index:5}
        .rsp-scan-status-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
        .rsp-dot-active{background:#10fbc4;box-shadow:0 0 8px #10fbc4;animation:blink 1.2s ease-in-out infinite}
        .rsp-dot-paused{background:#fbbf24;box-shadow:0 0 8px #fbbf24}
        .rsp-scan-overlay span{font-size:11px;color:#9ab2cf;font-family:'Space Mono',monospace;letter-spacing:.06em}
        .rsp-scanner-footer{display:flex;align-items:center;gap:8px;font-size:12px;color:#9ab2cf}
        .rsp-scanner-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
        .rsp-scanner-dot-on{background:#38bdf8;box-shadow:0 0 8px #38bdf8;animation:blink 1.5s ease-in-out infinite}
        .rsp-scanner-dot-off{background:#fbbf24;box-shadow:0 0 8px #fbbf24}
        .rsp-tips{display:flex;flex-direction:column;gap:10px}
        .rsp-tip{display:flex;align-items:center;gap:14px;padding:14px 18px;border-radius:14px;background:rgba(4,10,22,.6);border:1px solid rgba(56,189,248,.1);transition:border-color .2s ease,transform .2s ease}
        .rsp-tip:hover{border-color:rgba(56,189,248,.22);transform:translateX(4px)}
        .rsp-tip-icon{font-size:20px;flex-shrink:0}
        .rsp-tip-text{font-size:13px;color:#a8c0d8;line-height:1.5}
        .rsp-right{display:flex;flex-direction:column;gap:16px;justify-content:flex-start}
        .rsp-card{padding:32px;border-radius:26px;background:rgba(8,16,36,.95);border:1px solid rgba(56,189,248,.16);display:flex;flex-direction:column;gap:20px;box-shadow:0 0 40px rgba(56,189,248,.08)}
        .rsp-card-header{display:flex;align-items:flex-start;gap:16px}
        .rsp-card-icon{width:58px;height:58px;border-radius:16px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:28px;background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.2)}
        .rsp-card-badge{display:inline-flex;padding:5px 12px;border-radius:999px;background:rgba(16,251,196,.1);border:1px solid rgba(16,251,196,.22);color:#10fbc4;font-size:11px;font-weight:700;margin-bottom:8px;letter-spacing:.08em;text-transform:uppercase}
        .rsp-card-title{font-size:22px;font-weight:800;color:#fff}
        .rsp-input-wrap{position:relative;border-radius:16px;overflow:hidden;border:2px solid rgba(56,189,248,.18);transition:border-color .22s ease;background:rgba(4,10,22,.7)}
        .rsp-input-wrap.focused{border-color:rgba(56,189,248,.55);box-shadow:0 0 0 3px rgba(56,189,248,.1)}
        .rsp-input-wrap.has-err{border-color:rgba(255,77,109,.5);animation:rspShake .35s ease}
        .rsp-input-label{display:block;padding:12px 18px 0;font-family:'Space Mono',monospace;font-size:9px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:#6882a8}
        .rsp-input{width:100%;background:transparent;border:none;outline:none;padding:8px 52px 16px 18px;font-size:22px;font-weight:700;color:#fff;font-family:'Space Mono',monospace;letter-spacing:.04em}
        .rsp-input::placeholder{color:rgba(104,130,168,.4);font-weight:400;font-size:18px}
        .rsp-input-clear{position:absolute;right:16px;top:50%;transform:translateY(-50%);background:rgba(56,189,248,.12);border:1px solid rgba(56,189,248,.22);border-radius:50%;width:28px;height:28px;color:#6882a8;cursor:pointer;font-size:12px;display:flex;align-items:center;justify-content:center;transition:all .2s ease}
        .rsp-input-clear:hover{background:rgba(255,77,109,.18);color:#ff4d6d;border-color:rgba(255,77,109,.35)}
        .rsp-error{display:flex;gap:14px;align-items:flex-start;padding:16px 18px;border-radius:14px;background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.25);animation:rspShake .35s ease}
        .rsp-error-icon{font-size:20px;flex-shrink:0}
        .rsp-error-title{font-size:14px;font-weight:700;color:#ff4d6d;margin-bottom:4px}
        .rsp-error-body{font-size:13px;color:#c47080;line-height:1.6}
        .rsp-status-chips{display:flex;gap:10px;flex-wrap:wrap}
        .rsp-chip{display:flex;align-items:center;gap:8px;padding:8px 14px;border-radius:999px;background:rgba(56,189,248,.05);border:1px solid rgba(56,189,248,.12);font-size:12px;color:#4a6080;transition:all .22s ease}
        .rsp-chip.rsp-chip-on{background:rgba(16,251,196,.08);border-color:rgba(16,251,196,.25);color:#10fbc4}
        .rsp-chip.rsp-chip-loading{background:rgba(251,191,36,.08);border-color:rgba(251,191,36,.25);color:#fbbf24}
        .rsp-chip-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0;background:currentColor;opacity:.7}
        .rsp-submit-btn{width:100%;padding:18px 24px;border-radius:16px;border:none;font-size:16px;font-weight:700;cursor:pointer;font-family:'DM Sans',sans-serif;display:flex;align-items:center;justify-content:center;gap:10px;background:rgba(56,189,248,.08);border:2px solid rgba(56,189,248,.18);color:#6882a8;transition:all .25s ease}
        .rsp-submit-btn:disabled:not(.rsp-submit-ready){cursor:not-allowed}
        .rsp-submit-btn.rsp-submit-ready{background:linear-gradient(135deg,#059669,#10fbc4);border-color:transparent;color:#020810;box-shadow:0 6px 32px rgba(16,251,196,.45);font-size:17px}
        .rsp-submit-btn.rsp-submit-ready:hover{transform:translateY(-2px);box-shadow:0 14px 44px rgba(16,251,196,.6)}
        .rsp-btn-arrow{font-size:18px}
        .rsp-spinner{width:18px;height:18px;border-radius:50%;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;animation:rspSpin .7s linear infinite}
        .rsp-example-hint{display:flex;align-items:center;gap:10px;padding:14px 20px;border-radius:14px;background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.16);font-size:13px;color:#6882a8}
        .rsp-hint-icon{font-size:16px}
        .rsp-example-code{color:#fbbf24;font-family:'Space Mono',monospace;font-size:13px}
        @media(max-width:900px){.rsp-main{grid-template-columns:1fr}}
        @media(max-width:600px){.rsp-progress-bar{padding:16px;gap:0}.rsp-step-label{display:none}.rsp-card{padding:22px}}
      `}</style>
    </PageWrapper>
  );
}

export default ReceiptScanPage;