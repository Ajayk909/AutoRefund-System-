import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import PageWrapper from "../components/PageWrapper";

function Particles() {
  const particles = useMemo(
    () =>
      Array.from({ length: 28 }, (_, i) => ({
        id: i,
        left: `${3 + Math.random() * 94}%`,
        bottom: `${Math.random() * 18}%`,
        size: `${1.5 + Math.random() * 3.5}px`,
        duration: `${9 + Math.random() * 14}s`,
        delay: `${Math.random() * 10}s`,
        color: ["#10fbc4","#38bdf8","#60a5fa","#818cf8","#a78bfa"][i % 5],
      })),
    []
  );
  return (
    <div className="hp-particles" aria-hidden>
      {particles.map((p) => (
        <span key={p.id} style={{ left: p.left, bottom: p.bottom, width: p.size, height: p.size, "--dur": p.duration, "--delay": p.delay, "--pc": p.color }} />
      ))}
    </div>
  );
}

function Topbar() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="hp-topbar">
      <div className="hp-topbar-brand">
        <span className="hp-topbar-dot" />
        AutoRefund
      </div>
      <div className="hp-topbar-center">
        <span className="hp-topbar-tagline">Trusted by 500+ retail locations across North America</span>
      </div>
      <div className="hp-topbar-time">
        {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </div>
    </div>
  );
}

function AnimCounter({ target, suffix = "", duration = 1800 }) {
  const [val, setVal] = useState(0);
  const ref = useRef(null);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      obs.disconnect();
      let start = null;
      const step = (ts) => {
        if (!start) start = ts;
        const p = Math.min((ts - start) / duration, 1);
        const ease = 1 - Math.pow(1 - p, 3);
        setVal(Math.round(ease * target));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }, { threshold: 0.3 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [target, duration]);
  return <span ref={ref}>{val.toLocaleString()}{suffix}</span>;
}

function HomePage() {
  const navigate = useNavigate();
  const [hoveredCard, setHoveredCard] = useState(null);

  return (
    <PageWrapper>
      <Particles />
      <Topbar />

      <div className="hp-shell">

        {/* HERO */}
        <section className="hp-hero">
          <div className="hp-hero-glow hp-hero-glow-1" />
          <div className="hp-hero-glow hp-hero-glow-2" />
          <div className="hp-hero-glow hp-hero-glow-3" />

          <div className="hp-hero-badge">
            <span className="hp-hero-badge-dot" />
            Kiosk Active · System Ready
          </div>

          <h1 className="hp-hero-title">
            Returns made
            <br />
            <span className="hp-hero-title-accent">ridiculously easy</span>
          </h1>

          <p className="hp-hero-subtitle">
            AutoRefund is the world's first AI-powered weight-verified return kiosk.
            No staff needed. No paperwork. Just scan, weigh, and get your money back in seconds.
          </p>

          <div className="hp-hero-cta-row">
            <button className="hp-cta-primary" onClick={() => navigate("/customer/receipt")}>
              <span className="hp-cta-icon">🛍️</span>
              Start My Return
              <span className="hp-cta-arrow">→</span>
            </button>
            <button className="hp-cta-ghost" onClick={() => navigate("/employee/login")}>
              <span className="hp-cta-icon">🔐</span>
              Staff Login
            </button>
          </div>

          <div className="hp-hero-trust">
            <div className="hp-trust-item"><span className="hp-trust-icon">⚡</span> Instant processing</div>
            <div className="hp-trust-sep" />
            <div className="hp-trust-item"><span className="hp-trust-icon">🔒</span> Secure &amp; private</div>
            <div className="hp-trust-sep" />
            <div className="hp-trust-item"><span className="hp-trust-icon">✅</span> 99.4% accuracy</div>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section className="hp-section">
          <div className="hp-section-label">How It Works</div>
          <h2 className="hp-section-title">Return in 3 simple steps</h2>
          <p className="hp-section-sub">No queues. No arguments. No waiting for a manager.</p>

          <div className="hp-steps-row">
            {[
              { n: "01", icon: "📋", title: "Scan receipt", desc: "Type or scan your receipt number. We'll pull up your purchase instantly.", color: "#38bdf8" },
              { n: "02", icon: "📦", title: "Choose item", desc: "Pick the item you want to return from your purchase list.", color: "#10fbc4" },
              { n: "03", icon: "⚖️", title: "Place & weigh", desc: "Set it on the scale. Our AI verifies it automatically and processes your refund.", color: "#60a5fa" },
            ].map((step, i) => (
              <div key={i} className="hp-step-card" style={{ animationDelay: `${0.1 + i * 0.12}s` }}>
                <div className="hp-step-num" style={{ color: step.color }}>{step.n}</div>
                <div className="hp-step-icon-wrap" style={{ borderColor: `${step.color}33`, background: `${step.color}0d` }}>
                  <span className="hp-step-icon">{step.icon}</span>
                </div>
                <h3 className="hp-step-title" style={{ color: step.color }}>{step.title}</h3>
                <p className="hp-step-desc">{step.desc}</p>
                {i < 2 && <div className="hp-step-connector" />}
              </div>
            ))}
          </div>
        </section>

        {/* STATS */}
        <section className="hp-stats-section">
          <div className="hp-stats-inner">
            <div className="hp-stats-text">
              <div className="hp-section-label">By the numbers</div>
              <h2 className="hp-section-title hp-stats-title">Trusted at scale</h2>
              <p className="hp-section-sub">
                AutoRefund has been processing returns since 2019 and has grown to become North America's most deployed return kiosk platform.
              </p>
              <button className="hp-cta-primary" style={{ marginTop: 28, width: "fit-content" }} onClick={() => navigate("/customer/receipt")}>
                Start a Return →
              </button>
            </div>
            <div className="hp-stats-grid">
              {[
                { val: 2400000, suffix: "+", label: "Refunds processed", color: "#10fbc4" },
                { val: 500, suffix: "+", label: "Retail partners", color: "#38bdf8" },
                { val: 99, suffix: ".4%", label: "Accuracy rate", color: "#60a5fa" },
                { val: 18, suffix: "s", label: "Average return time", color: "#a78bfa" },
              ].map((s, i) => (
                <div key={i} className="hp-stat-card" style={{ animationDelay: `${0.08 + i * 0.1}s` }}>
                  <div className="hp-stat-val" style={{ color: s.color }}>
                    <AnimCounter target={s.val} suffix={s.suffix} />
                  </div>
                  <div className="hp-stat-label">{s.label}</div>
                  <div className="hp-stat-bar" style={{ background: `${s.color}22` }}>
                    <div className="hp-stat-bar-fill" style={{ background: s.color }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CHOOSE PATH */}
        <section className="hp-section hp-choose-section">
          <div className="hp-section-label">Get started</div>
          <h2 className="hp-section-title">Who are you today?</h2>
          <p className="hp-section-sub">Select the option that fits you and we'll guide you through the process step by step.</p>

          <div className="hp-card-duo">
            <div
              className={`hp-path-card hp-path-customer ${hoveredCard === "customer" ? "hovered" : ""}`}
              onMouseEnter={() => setHoveredCard("customer")}
              onMouseLeave={() => setHoveredCard(null)}
              onClick={() => navigate("/customer/receipt")}
              role="button" tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && navigate("/customer/receipt")}
            >
              <div className="hp-path-glow hp-path-glow-green" />
              <div className="hp-path-icon-ring hp-path-ring-green">🛍️</div>
              <div className="hp-path-tag hp-path-tag-green">Customer</div>
              <h2 className="hp-path-title">I want to return an item</h2>
              <p className="hp-path-desc">Have your receipt handy and we'll walk you through the whole return process in under a minute.</p>
              <ul className="hp-path-features">
                <li><span className="hp-feat-check hp-feat-check-green">✓</span> Scan or type your receipt</li>
                <li><span className="hp-feat-check hp-feat-check-green">✓</span> Weight verified automatically</li>
                <li><span className="hp-feat-check hp-feat-check-green">✓</span> Refund in 3–5 business days</li>
              </ul>
              <button className="hp-path-btn hp-path-btn-green" onClick={(e) => { e.stopPropagation(); navigate("/customer/receipt"); }}>
                Start My Return →
              </button>
            </div>

            <div
              className={`hp-path-card hp-path-employee ${hoveredCard === "employee" ? "hovered" : ""}`}
              onMouseEnter={() => setHoveredCard("employee")}
              onMouseLeave={() => setHoveredCard(null)}
              onClick={() => navigate("/employee/login")}
              role="button" tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && navigate("/employee/login")}
            >
              <div className="hp-path-glow hp-path-glow-blue" />
              <div className="hp-path-icon-ring hp-path-ring-blue">🔐</div>
              <div className="hp-path-tag hp-path-tag-blue">Staff Only</div>
              <h2 className="hp-path-title">I work here</h2>
              <p className="hp-path-desc">Access the employee dashboard to review refund logs, handle pending requests, and manage the return queue.</p>
              <ul className="hp-path-features">
                <li><span className="hp-feat-check hp-feat-check-blue">✓</span> Review pending refunds</li>
                <li><span className="hp-feat-check hp-feat-check-blue">✓</span> Approve or reject requests</li>
                <li><span className="hp-feat-check hp-feat-check-blue">✓</span> Full refund history logs</li>
              </ul>
              <button className="hp-path-btn hp-path-btn-blue" onClick={(e) => { e.stopPropagation(); navigate("/employee/login"); }}>
                Employee Login →
              </button>
            </div>
          </div>
        </section>

        {/* FOOTER */}
        <footer className="hp-footer">
          <div className="hp-footer-brand"><span className="hp-footer-dot" />AutoRefund</div>
          <p className="hp-footer-tagline">Smarter returns. Happier customers. Less fraud.</p>
          <div className="hp-footer-meta">
            <span>© 2025 AutoRefund Inc. · Brampton, Ontario, Canada</span>
            <span className="hp-footer-sep">·</span>
            <span>v2.4.1</span>
            <span className="hp-footer-sep">·</span>
            <span className="hp-footer-status"><span className="hp-footer-online" />System Online</span>
          </div>
        </footer>
      </div>

      <style>{`
        .hp-particles{position:fixed;inset:0;pointer-events:none;z-index:0;overflow:hidden}
        .hp-particles span{
          position:absolute;border-radius:50%;background:var(--pc,#38bdf8);opacity:0;
          animation:hpFloat var(--dur,12s) var(--delay,0s) ease-in infinite;
        }
        @keyframes hpFloat{
          0%{opacity:0;transform:translateY(0) scale(0)}
          8%{opacity:.65;transform:translateY(-4vh) scale(1)}
          90%{opacity:.1}100%{opacity:0;transform:translateY(-90vh) scale(.1)}
        }
        .hp-topbar{
          position:fixed;top:0;left:0;right:0;z-index:100;height:60px;
          display:flex;align-items:center;justify-content:space-between;padding:0 36px;
          background:rgba(2,8,16,0.85);backdrop-filter:blur(28px);
          border-bottom:1px solid rgba(56,189,248,.12);
          box-shadow:0 1px 30px rgba(0,0,0,0.5);
        }
        .hp-topbar-brand{
          font-family:'Orbitron',sans-serif;font-size:13px;font-weight:700;
          letter-spacing:.18em;color:#38bdf8;text-transform:uppercase;
          display:flex;align-items:center;gap:10px;
        }
        .hp-topbar-dot{
          width:9px;height:9px;border-radius:50%;
          background:#10fbc4;box-shadow:0 0 12px #10fbc4,0 0 24px rgba(16,251,196,.4);
          animation:hpDotPulse 2s ease-in-out infinite;
        }
        @keyframes hpDotPulse{0%,100%{box-shadow:0 0 8px #10fbc4}50%{box-shadow:0 0 22px #10fbc4,0 0 44px rgba(16,251,196,.4)}}
        .hp-topbar-center{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:rgba(100,140,200,.5)}
        .hp-topbar-time{font-family:'Space Mono',monospace;font-size:13px;color:#38bdf8;letter-spacing:.08em;opacity:.9}
        .hp-shell{position:relative;z-index:1;min-height:100vh;padding-top:60px;display:flex;flex-direction:column}
        .hp-hero{
          position:relative;overflow:hidden;
          display:flex;flex-direction:column;align-items:center;text-align:center;
          padding:120px 24px 100px;gap:30px;
        }
        .hp-hero-glow{position:absolute;border-radius:50%;pointer-events:none;filter:blur(80px)}
        .hp-hero-glow-1{width:700px;height:700px;top:-200px;left:50%;transform:translateX(-50%);background:radial-gradient(circle,rgba(56,189,248,.18),transparent 70%)}
        .hp-hero-glow-2{width:450px;height:450px;bottom:-120px;left:8%;background:radial-gradient(circle,rgba(16,251,196,.12),transparent 70%)}
        .hp-hero-glow-3{width:350px;height:350px;bottom:0;right:4%;background:radial-gradient(circle,rgba(167,139,250,.1),transparent 70%)}
        .hp-hero-badge{
          display:inline-flex;align-items:center;gap:10px;padding:10px 20px;border-radius:999px;
          background:rgba(16,251,196,.1);border:1px solid rgba(16,251,196,.28);
          color:#10fbc4;font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
          animation:hpUp .6s ease both .05s;box-shadow:0 0 24px rgba(16,251,196,.15);
        }
        .hp-hero-badge-dot{width:7px;height:7px;border-radius:50%;background:#10fbc4;animation:hpDotPulse 1.5s ease-in-out infinite}
        .hp-hero-title{
          font-family:'Orbitron',sans-serif;
          font-size:clamp(38px,5.8vw,76px);font-weight:900;line-height:1.06;letter-spacing:-.02em;color:#fff;
          animation:hpUp .65s ease both .12s;
        }
        .hp-hero-title-accent{
          background:linear-gradient(135deg,#10fbc4 0%,#38bdf8 50%,#a78bfa 100%);
          -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
        }
        .hp-hero-subtitle{font-size:clamp(14px,1.7vw,19px);color:#9db0ce;max-width:600px;line-height:1.75;animation:hpUp .65s ease both .2s}
        .hp-hero-cta-row{display:flex;gap:16px;flex-wrap:wrap;justify-content:center;animation:hpUp .65s ease both .28s}
        .hp-cta-primary{
          display:flex;align-items:center;gap:12px;padding:20px 38px;border-radius:16px;border:none;
          background:linear-gradient(135deg,#059669,#10fbc4);
          color:#020810;font-size:17px;font-weight:800;cursor:pointer;font-family:'DM Sans',sans-serif;
          box-shadow:0 8px 36px rgba(16,251,196,.45),inset 0 1px 0 rgba(255,255,255,.3);
          transition:transform .22s ease,box-shadow .22s ease;
        }
        .hp-cta-primary:hover{transform:translateY(-3px);box-shadow:0 18px 52px rgba(16,251,196,.6)}
        .hp-cta-ghost{
          display:flex;align-items:center;gap:10px;padding:20px 32px;border-radius:16px;
          background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.28);
          color:#8ddcff;font-size:16px;font-weight:600;cursor:pointer;font-family:'DM Sans',sans-serif;
          transition:all .22s ease;
        }
        .hp-cta-ghost:hover{background:rgba(56,189,248,.16);border-color:rgba(56,189,248,.5);color:#38bdf8;transform:translateY(-2px);box-shadow:0 0 24px rgba(56,189,248,.2)}
        .hp-cta-icon{font-size:20px}
        .hp-cta-arrow{font-size:18px}
        .hp-hero-trust{display:flex;align-items:center;gap:20px;flex-wrap:wrap;justify-content:center;animation:hpUp .65s ease both .36s}
        .hp-trust-item{display:flex;align-items:center;gap:8px;font-size:13px;color:#6882a8}
        .hp-trust-icon{font-size:15px}
        .hp-trust-sep{width:1px;height:16px;background:rgba(56,189,248,.2)}
        .hp-section{padding:88px 48px;max-width:1260px;width:100%;margin:0 auto}
        .hp-section-label{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.22em;text-transform:uppercase;color:#38bdf8;opacity:.9;margin-bottom:14px}
        .hp-section-title{font-family:'Orbitron',sans-serif;font-size:clamp(24px,3.2vw,46px);font-weight:800;color:#fff;margin-bottom:14px;letter-spacing:-.02em}
        .hp-section-sub{font-size:16px;color:#7fa4d9;line-height:1.7;max-width:580px}
        .hp-steps-row{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:52px;position:relative}
        .hp-step-card{
          position:relative;padding:34px 30px;border-radius:26px;
          background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);
          animation:hpUp .55s ease both;
          transition:transform .24s ease,border-color .24s ease,box-shadow .24s ease;
        }
        .hp-step-card:hover{transform:translateY(-8px);box-shadow:0 28px 64px rgba(0,0,0,.3);border-color:rgba(56,189,248,.25)}
        .hp-step-num{font-family:'Orbitron',sans-serif;font-size:11px;letter-spacing:.2em;text-transform:uppercase;margin-bottom:20px;opacity:.8}
        .hp-step-icon-wrap{width:72px;height:72px;border-radius:20px;display:flex;align-items:center;justify-content:center;border:1px solid;margin-bottom:20px;transition:transform .22s ease}
        .hp-step-card:hover .hp-step-icon-wrap{transform:scale(1.1) rotate(4deg)}
        .hp-step-icon{font-size:32px}
        .hp-step-title{font-size:20px;font-weight:700;margin-bottom:12px}
        .hp-step-desc{font-size:14px;color:#7fa4d9;line-height:1.75}
        .hp-step-connector{position:absolute;top:52px;right:-14px;width:28px;height:2px;background:linear-gradient(90deg,rgba(56,189,248,.35),rgba(56,189,248,.08));z-index:2}
        .hp-stats-section{
          background:linear-gradient(135deg,rgba(8,16,36,.98),rgba(4,10,22,.95));
          border-top:1px solid rgba(56,189,248,.1);border-bottom:1px solid rgba(56,189,248,.1);
          padding:88px 48px;
        }
        .hp-stats-inner{max-width:1260px;margin:0 auto;display:grid;grid-template-columns:1fr 1.4fr;gap:64px;align-items:center}
        .hp-stats-title{margin-bottom:18px}
        .hp-stats-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}
        .hp-stat-card{
          padding:28px 24px;border-radius:22px;
          background:rgba(4,10,22,.8);border:1px solid rgba(56,189,248,.12);
          animation:hpUp .5s ease both;transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease;
        }
        .hp-stat-card:hover{transform:translateY(-5px);border-color:rgba(56,189,248,.28);box-shadow:0 16px 48px rgba(0,0,0,.3)}
        .hp-stat-val{font-family:'Orbitron',sans-serif;font-size:40px;font-weight:900;line-height:1;margin-bottom:10px}
        .hp-stat-label{font-size:13px;color:#6882a8;margin-bottom:16px}
        .hp-stat-bar{height:4px;border-radius:999px;overflow:hidden}
        .hp-stat-bar-fill{height:100%;width:75%;border-radius:999px;animation:hpGrow 1.4s ease both .5s}
        @keyframes hpGrow{from{width:0}}
        .hp-choose-section{text-align:center}
        .hp-choose-section .hp-section-sub{max-width:520px;margin:0 auto}
        .hp-card-duo{display:grid;grid-template-columns:repeat(2,1fr);gap:26px;margin-top:52px;text-align:left}
        .hp-path-card{
          position:relative;overflow:hidden;padding:44px;border-radius:30px;
          background:rgba(8,16,36,.95);border:1px solid rgba(56,189,248,.12);
          cursor:pointer;display:flex;flex-direction:column;gap:20px;
          transition:transform .28s ease,border-color .28s ease,box-shadow .28s ease;
          animation:hpUp .55s ease both;
        }
        .hp-path-card.hovered{transform:translateY(-7px);box-shadow:0 32px 72px rgba(0,0,0,.35)}
        .hp-path-customer.hovered{border-color:rgba(16,251,196,.4)}
        .hp-path-employee.hovered{border-color:rgba(96,165,250,.4)}
        .hp-path-glow{position:absolute;width:380px;height:380px;border-radius:50%;top:-110px;right:-90px;filter:blur(65px);pointer-events:none;opacity:0;transition:opacity .4s ease}
        .hp-path-card.hovered .hp-path-glow{opacity:1}
        .hp-path-glow-green{background:radial-gradient(circle,rgba(16,251,196,.18),transparent 70%)}
        .hp-path-glow-blue{background:radial-gradient(circle,rgba(96,165,250,.16),transparent 70%)}
        .hp-path-icon-ring{width:82px;height:82px;border-radius:24px;display:flex;align-items:center;justify-content:center;font-size:38px;border:1px solid;flex-shrink:0;transition:transform .28s ease}
        .hp-path-card.hovered .hp-path-icon-ring{transform:scale(1.12) rotate(-4deg)}
        .hp-path-ring-green{background:rgba(16,251,196,.1);border-color:rgba(16,251,196,.28)}
        .hp-path-ring-blue{background:rgba(96,165,250,.1);border-color:rgba(96,165,250,.28)}
        .hp-path-tag{display:inline-flex;width:fit-content;padding:6px 14px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;border:1px solid}
        .hp-path-tag-green{background:rgba(16,251,196,.1);border-color:rgba(16,251,196,.25);color:#10fbc4}
        .hp-path-tag-blue{background:rgba(96,165,250,.1);border-color:rgba(96,165,250,.25);color:#60a5fa}
        .hp-path-title{font-size:28px;font-weight:800;color:#fff}
        .hp-path-desc{font-size:15px;color:#8aa4c4;line-height:1.75}
        .hp-path-features{list-style:none;padding:0;display:flex;flex-direction:column;gap:10px}
        .hp-path-features li{display:flex;align-items:center;gap:10px;font-size:14px;color:#b2c8e4}
        .hp-feat-check{width:22px;height:22px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
        .hp-feat-check-green{background:rgba(16,251,196,.14);color:#10fbc4;border:1px solid rgba(16,251,196,.25)}
        .hp-feat-check-blue{background:rgba(96,165,250,.14);color:#60a5fa;border:1px solid rgba(96,165,250,.25)}
        .hp-path-btn{margin-top:auto;padding:17px 30px;border-radius:14px;border:none;font-size:15px;font-weight:700;cursor:pointer;font-family:'DM Sans',sans-serif;transition:transform .22s ease,box-shadow .22s ease}
        .hp-path-btn:hover{transform:translateY(-2px)}
        .hp-path-btn-green{background:linear-gradient(135deg,#059669,#10fbc4);color:#020810;box-shadow:0 5px 24px rgba(16,251,196,.35)}
        .hp-path-btn-green:hover{box-shadow:0 12px 40px rgba(16,251,196,.55)}
        .hp-path-btn-blue{background:linear-gradient(135deg,#2563eb,#60a5fa);color:#fff;box-shadow:0 5px 24px rgba(96,165,250,.35)}
        .hp-path-btn-blue:hover{box-shadow:0 12px 40px rgba(96,165,250,.55)}
        .hp-footer{border-top:1px solid rgba(56,189,248,.1);padding:52px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:12px}
        .hp-footer-brand{font-family:'Orbitron',sans-serif;font-size:15px;font-weight:700;letter-spacing:.18em;color:#38bdf8;text-transform:uppercase;display:flex;align-items:center;gap:10px}
        .hp-footer-dot{width:8px;height:8px;border-radius:50%;background:#10fbc4;box-shadow:0 0 12px #10fbc4}
        .hp-footer-tagline{font-size:14px;color:#6882a8}
        .hp-footer-meta{display:flex;align-items:center;gap:12px;font-size:12px;color:#4a6080;flex-wrap:wrap;justify-content:center}
        .hp-footer-sep{opacity:.4}
        .hp-footer-status{display:flex;align-items:center;gap:6px}
        .hp-footer-online{width:6px;height:6px;border-radius:50%;background:#10fbc4;box-shadow:0 0 8px #10fbc4}
        @keyframes hpUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
        @media(max-width:1100px){.hp-stats-inner{grid-template-columns:1fr;gap:40px}}
        @media(max-width:900px){.hp-steps-row,.hp-card-duo{grid-template-columns:1fr}.hp-step-connector{display:none}.hp-stats-grid{grid-template-columns:repeat(2,1fr)}.hp-section,.hp-stats-section{padding:64px 24px}}
        @media(max-width:600px){.hp-topbar{padding:0 16px}.hp-topbar-center{display:none}.hp-hero{padding:90px 20px 70px}.hp-hero-cta-row{flex-direction:column;align-items:stretch}.hp-hero-trust{flex-direction:column;gap:10px}.hp-trust-sep{display:none}.hp-stats-grid{grid-template-columns:1fr}.hp-path-card{padding:28px 22px}}
      `}</style>
    </PageWrapper>
  );
}

export default HomePage;