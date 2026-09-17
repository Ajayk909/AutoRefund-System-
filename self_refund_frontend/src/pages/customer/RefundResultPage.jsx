import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";

function KioskShell() {
  const [time, setTime] = useState(new Date());
  const particles = useMemo(() => Array.from({ length: 20 }, (_, i) => ({ id: i, left: `${4 + Math.random() * 92}%`, bottom: `${Math.random() * 15}%`, size: `${2 + Math.random() * 4}px`, duration: `${9 + Math.random() * 12}s`, delay: `${Math.random() * 8}s`, color: i % 3 === 0 ? "#10fbc4" : i % 3 === 1 ? "#38bdf8" : "#fbbf24" })), []);
  useEffect(() => { const t = setInterval(() => setTime(new Date()), 1000); return () => clearInterval(t); }, []);
  return (
    <>
      <div className="kiosk-particles" aria-hidden>{particles.map((p) => (<span key={p.id} style={{ left: p.left, bottom: p.bottom, width: p.size, height: p.size, "--dur": p.duration, "--delay": p.delay, "--pc": p.color }} />))}</div>
      <div className="kiosk-topbar">
        <div className="topbar-brand"><span className="topbar-dot" />AutoRefund</div>
        <div className="topbar-time">{time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
        <div className="topbar-status">● CUSTOMER MODE</div>
      </div>
    </>
  );
}

function Confetti() {
  const pieces = useMemo(() => Array.from({ length: 40 }, (_, i) => ({ id: i, x: `${Math.random() * 100}%`, color: ["#10fbc4","#38bdf8","#fbbf24","#60a5fa","#f472b6","#a78bfa"][i % 6], size: `${4 + Math.random() * 7}px`, delay: `${Math.random() * 1}s`, duration: `${1.2 + Math.random() * 1}s`, rotation: `${Math.random() * 720}deg` })), []);
  return (
    <div className="rr2-confetti" aria-hidden>
      {pieces.map(p => (<span key={p.id} style={{ left: p.x, background: p.color, width: p.size, height: p.size, "--delay": p.delay, "--dur": p.duration, "--rot": p.rotation }} />))}
    </div>
  );
}

function RefundResultPage() {
  const [result, setResult] = useState(null);
  const [show, setShow] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const saved = localStorage.getItem("refundResult");
    if (saved) { setResult(JSON.parse(saved)); setTimeout(() => setShow(true), 150); }
  }, []);

  if (!result) {
    return (
      <PageWrapper><KioskShell />
        <Layout title="Refund Result" subtitle="No result found.">
          <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: "40px 0" }}>
            <button className="primary-btn" onClick={() => navigate("/")}>🏠 Return Home</button>
            <button className="ghost-btn" onClick={() => navigate("/customer/receipt")}>Start New Return</button>
          </div>
        </Layout>
      </PageWrapper>
    );
  }

  const approved = result.decision_status === "approved";
  const accent = approved ? "#10fbc4" : "#fbbf24";

  const resetAndGoHome = () => {
    localStorage.removeItem("transactionData");
    localStorage.removeItem("selectedItem");
    localStorage.removeItem("refundResult");
    navigate("/");
  };

  return (
    <PageWrapper>
      <KioskShell />
      {approved && show && <Confetti />}
      <Layout title="" subtitle="">
        <div className={`kiosk-content rr2-page ${show ? "rr2-visible" : ""}`}>

          {/* Progress complete */}
          <div className="rr2-progress-complete">
            {["Receipt scanned", "Item selected", "Weight verified", "Refund submitted"].map((s, i) => (
              <div key={i} className="rr2-done-step">
                <div className="rr2-done-check">✓</div>
                <span>{s}</span>
              </div>
            ))}
          </div>

          {/* Hero */}
          <div className={`rr2-hero ${approved ? "rr2-hero-approved" : "rr2-hero-pending"}`}>
            <div className="rr2-hero-glow" style={{ background: `radial-gradient(circle, ${accent}1a, transparent 70%)` }} />
            <div className="rr2-icon-ring" style={{ borderColor: `${accent}40`, boxShadow: `0 0 70px ${accent}28` }}>
              <span className="rr2-icon" style={{ color: accent }}>{approved ? "✓" : "⏳"}</span>
            </div>
            <div className="rr2-hero-text">
              <div className="rr2-hero-eyebrow" style={{ color: accent }}>{approved ? "🎉 Refund Approved!" : "⏳ Under Review"}</div>
              <h1 className="rr2-hero-title">{approved ? "You're all set!" : "Almost there"}</h1>
              <p className="rr2-hero-subtitle">
                {approved ? "Your refund has been automatically approved and is on its way back to you." : "Your refund request has been submitted and is waiting for a quick staff review."}
              </p>
            </div>
            <div className="rr2-amount-card" style={{ borderColor: `${accent}30`, background: `${accent}09` }}>
              <div className="rr2-amount-label">Refund Amount</div>
              <div className="rr2-amount-val" style={{ color: accent }}>${result.refund_amount}</div>
              <div className="rr2-amount-status" style={{ background: `${accent}14`, color: accent, borderColor: `${accent}28` }}>
                {approved ? "✓ Processing" : "⏳ Pending review"}
              </div>
            </div>
          </div>

          {/* Details grid */}
          <div className="rr2-details-grid">
            {[
              { label: "Expected Weight", val: `${result.expected_weight_grams} g` },
              { label: "Measured Weight", val: `${result.measured_weight_grams} g` },
              { label: "Verification", val: approved ? "Auto-approved" : "Manual review", color: approved ? "#10fbc4" : "#fbbf24" },
              { label: "Decision Reason", val: result.decision_reason },
            ].map((d, i) => (
              <div key={i} className="rr2-detail-card">
                <span>{d.label}</span>
                <strong style={d.color ? { color: d.color } : {}}>{d.val}</strong>
              </div>
            ))}
          </div>

          {/* Next steps */}
          <div className="rr2-next-card" style={{ borderColor: `${accent}22`, background: `${accent}06` }}>
            <div className="rr2-next-icon">{approved ? "📬" : "👤"}</div>
            <div className="rr2-next-body">
              <div className="rr2-next-title" style={{ color: accent }}>{approved ? "What happens next" : "What to expect"}</div>
              <p className="rr2-next-desc">
                {approved ? `Your refund of $${result.refund_amount} will be returned to your original payment method within 3–5 business days. You'll receive a confirmation email shortly.` : "A staff member will review your request, usually within 24 hours. You'll be notified by email once a decision is made. No further action needed from you."}
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="rr2-actions">
            <button className="rr2-new-btn" onClick={resetAndGoHome}>
              <span>🔄</span> Start a New Return
            </button>
            <button className="ghost-btn" onClick={() => navigate(-1)}>← Review Details</button>
            <button className="ghost-btn" onClick={() => navigate("/")}>🏠 Home</button>
          </div>
        </div>
      </Layout>

      <style>{`
        @keyframes rr2Up{from{opacity:0;transform:translateY(20px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}
        @keyframes rr2Confetti{0%{transform:translateY(-10px) rotate(0deg);opacity:1}100%{transform:translateY(110vh) rotate(var(--rot));opacity:0}}
        @keyframes rr2Bounce{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
        .rr2-confetti{position:fixed;inset:0;pointer-events:none;z-index:200;overflow:hidden}
        .rr2-confetti span{position:absolute;top:-10px;border-radius:2px;animation:rr2Confetti var(--dur,1.5s) var(--delay,0s) ease-in forwards}
        .rr2-page{min-height:calc(100vh - 110px);display:flex;flex-direction:column;gap:20px;opacity:0;transition:opacity .5s ease}
        .rr2-visible{opacity:1}
        .rr2-progress-complete{display:flex;gap:10px;flex-wrap:wrap;animation:rr2Up .5s ease both}
        .rr2-done-step{display:flex;align-items:center;gap:8px;padding:10px 16px;border-radius:999px;background:rgba(16,251,196,.09);border:1px solid rgba(16,251,196,.22);font-size:13px;color:#10fbc4;font-weight:600}
        .rr2-done-check{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:rgba(16,251,196,.18);font-size:11px;font-weight:900;flex-shrink:0}
        .rr2-hero{position:relative;overflow:hidden;padding:48px 40px;border-radius:28px;display:flex;align-items:center;gap:36px;flex-wrap:wrap;border:1px solid;animation:rr2Up .55s ease both .06s}
        .rr2-hero-approved{background:linear-gradient(135deg,rgba(16,251,196,.08),rgba(16,251,196,.02));border-color:rgba(16,251,196,.28)}
        .rr2-hero-pending{background:linear-gradient(135deg,rgba(251,191,36,.09),rgba(251,191,36,.02));border-color:rgba(251,191,36,.28)}
        .rr2-hero-glow{position:absolute;width:550px;height:550px;top:-160px;right:-110px;border-radius:50%;filter:blur(85px);pointer-events:none}
        .rr2-icon-ring{width:115px;height:115px;border-radius:50%;border:2px solid;flex-shrink:0;display:flex;align-items:center;justify-content:center;background:rgba(4,10,22,.65);animation:rr2Bounce 2.5s ease-in-out infinite}
        .rr2-icon{font-size:52px;font-weight:900}
        .rr2-hero-text{flex:1;min-width:250px}
        .rr2-hero-eyebrow{font-size:14px;font-weight:800;letter-spacing:.06em;margin-bottom:10px}
        .rr2-hero-title{font-family:'Orbitron',sans-serif;font-size:clamp(28px,4vw,54px);font-weight:900;color:#fff;margin-bottom:12px}
        .rr2-hero-subtitle{font-size:16px;color:#9db0ce;line-height:1.7;max-width:480px}
        .rr2-amount-card{padding:28px 36px;border-radius:22px;border:1px solid;text-align:center;flex-shrink:0;min-width:180px}
        .rr2-amount-label{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:#6882a8;margin-bottom:10px}
        .rr2-amount-val{font-family:'Orbitron',sans-serif;font-size:50px;font-weight:900;line-height:1;margin-bottom:14px}
        .rr2-amount-status{display:inline-flex;padding:7px 16px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid;font-family:'Space Mono',monospace;letter-spacing:.06em;text-transform:uppercase}
        .rr2-details-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;animation:rr2Up .5s ease both .14s}
        .rr2-detail-card{padding:20px 18px;border-radius:18px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);transition:transform .22s ease,border-color .22s ease}
        .rr2-detail-card:hover{transform:translateY(-3px);border-color:rgba(56,189,248,.25)}
        .rr2-detail-card span{display:block;font-family:'Space Mono',monospace;font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#6882a8;margin-bottom:10px}
        .rr2-detail-card strong{color:#fff;font-size:16px}
        .rr2-next-card{display:flex;align-items:flex-start;gap:20px;padding:24px 28px;border-radius:20px;border:1px solid;animation:rr2Up .5s ease both .2s}
        .rr2-next-icon{font-size:32px;flex-shrink:0;margin-top:2px}
        .rr2-next-title{font-size:16px;font-weight:800;margin-bottom:10px}
        .rr2-next-desc{font-size:14px;color:#9db0ce;line-height:1.75}
        .rr2-actions{display:flex;gap:14px;flex-wrap:wrap;animation:rr2Up .5s ease both .28s}
        .rr2-new-btn{display:flex;align-items:center;gap:10px;padding:16px 32px;border-radius:16px;border:none;background:linear-gradient(135deg,#0ea5e9,#38bdf8);color:#020810;font-size:16px;font-weight:800;cursor:pointer;font-family:'DM Sans',sans-serif;box-shadow:0 6px 32px rgba(56,189,248,.45);transition:transform .22s ease,box-shadow .22s ease}
        .rr2-new-btn:hover{transform:translateY(-2px);box-shadow:0 14px 44px rgba(56,189,248,.6)}
        @media(max-width:900px){.rr2-hero{flex-direction:column;align-items:flex-start;gap:24px}.rr2-details-grid{grid-template-columns:repeat(2,1fr)}}
        @media(max-width:600px){.rr2-hero{padding:28px 22px}.rr2-details-grid{grid-template-columns:1fr}.rr2-amount-val{font-size:42px}.rr2-actions{flex-direction:column}.rr2-new-btn{width:100%;justify-content:center}}
      `}</style>
    </PageWrapper>
  );
}

export default RefundResultPage;