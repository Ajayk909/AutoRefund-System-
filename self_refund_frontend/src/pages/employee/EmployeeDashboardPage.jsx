import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";

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
        <div className="topbar-status">● EMPLOYEE MODE</div>
      </div>
    </>
  );
}

function EmployeeDashboardPage() {
  const navigate = useNavigate();
  const staff = JSON.parse(localStorage.getItem("staffUser") || "{}");

  return (
    <PageWrapper>
      <KioskShell />
      <Layout title="" subtitle="">
        <div className="kiosk-content ed-page">
          <div className="ed-top-row">
            <div className="kiosk-hero ed-hero" style={{ textAlign: "left", padding: "32px 0 24px" }}>
              <div className="kiosk-eyebrow">Employee Dashboard</div>
              <h1 className="page-title">Welcome Back{staff.name ? `, ${staff.name}` : ""}</h1>
              <p className="page-subtitle">Jump into the refund tools below to manage the queue and review history.</p>
            </div>
            <div className="ed-top-actions">
              <button className="ghost-btn" onClick={() => navigate("/")}>🏠 Main Menu</button>
              <button className="ghost-btn" onClick={() => { localStorage.removeItem("staffUser"); navigate("/employee/login"); }}>Sign Out →</button>
            </div>
          </div>

          <div className="ed-main-grid">
            <section className="ed-feature-card ed-logs" onClick={() => navigate("/employee/logs")} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && navigate("/employee/logs")}>
              <div className="ed-feature-glow ed-glow-blue" />
              <div className="ed-feature-icon">📊</div>
              <div className="ed-feature-body">
                <div className="ed-feature-badge ed-badge-blue">Refund Logs</div>
                <h2>View refund history</h2>
                <p>Open the full refund log, review dates, and filter records by date range.</p>
              </div>
              <div className="ed-feature-footer">
                <span>History, status, timestamps</span>
                <button className="primary-btn" onClick={(e) => { e.stopPropagation(); navigate("/employee/logs"); }}>Open Logs →</button>
              </div>
            </section>

            <section className="ed-feature-card ed-pending" onClick={() => navigate("/employee/pending")} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && navigate("/employee/pending")}>
              <div className="ed-feature-glow ed-glow-amber" />
              <div className="ed-feature-icon">⏳</div>
              <div className="ed-feature-body">
                <div className="ed-feature-badge ed-badge-amber">Pending Queue</div>
                <h2>Review flagged refunds</h2>
                <p>Approve or reject refunds that could not be resolved automatically by the system.</p>
              </div>
              <div className="ed-feature-footer">
                <span>Manual review workflow</span>
                <button className="secondary-btn" onClick={(e) => { e.stopPropagation(); navigate("/employee/pending"); }}>Review Queue →</button>
              </div>
            </section>
          </div>

          <div className="ed-stats-grid">
            {[
              { label: "System", val: "Online", color: "green" },
              { label: "Scale", val: "Connected", color: "green" },
              { label: "Camera", val: "Pending", color: "amber" },
              { label: "Role", val: "Staff", color: null },
            ].map((s, i) => (
              <div key={i} className="ed-stat-card">
                <span>{s.label}</span>
                <strong className={s.color || ""}>{s.val}</strong>
              </div>
            ))}
          </div>
        </div>
      </Layout>

      <style>{`
        @keyframes edUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
        .ed-page{min-height:calc(100vh - 110px)}
        .ed-top-row{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:16px}
        .ed-top-actions{display:flex;gap:12px;flex-wrap:wrap}
        .ed-main-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:22px;margin-top:8px}
        .ed-feature-card{
          position:relative;overflow:hidden;display:flex;flex-direction:column;gap:20px;padding:30px;border-radius:28px;
          background:rgba(8,16,36,.95);border:1px solid rgba(56,189,248,.12);
          transition:transform .24s ease,border-color .24s ease,box-shadow .24s ease;cursor:pointer;
          animation:edUp .45s ease both;
        }
        .ed-feature-card:hover{transform:translateY(-5px);box-shadow:0 24px 52px rgba(0,0,0,.25)}
        .ed-logs:hover{border-color:rgba(96,165,250,.35)}
        .ed-pending:hover{border-color:rgba(251,191,36,.32)}
        .ed-feature-glow{position:absolute;width:280px;height:280px;right:-60px;top:-60px;border-radius:50%;filter:blur(70px);pointer-events:none;opacity:0;transition:opacity .35s ease}
        .ed-feature-card:hover .ed-feature-glow{opacity:1}
        .ed-glow-blue{background:radial-gradient(circle,rgba(96,165,250,.18),transparent 70%)}
        .ed-glow-amber{background:radial-gradient(circle,rgba(251,191,36,.16),transparent 70%)}
        .ed-feature-icon{width:72px;height:72px;border-radius:22px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);font-size:34px;transition:transform .24s ease}
        .ed-feature-card:hover .ed-feature-icon{transform:scale(1.08) rotate(-3deg)}
        .ed-feature-badge{display:inline-flex;width:fit-content;padding:7px 12px;border-radius:999px;font-size:12px;font-weight:700;margin-bottom:12px;letter-spacing:.06em}
        .ed-badge-blue{background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.22);color:#8ddcff}
        .ed-badge-amber{background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.22);color:#fbbf24}
        .ed-feature-body h2{font-size:28px;color:#fff;margin-bottom:10px}
        .ed-feature-body p{color:#9db0ce;line-height:1.75;font-size:15px}
        .ed-feature-footer{margin-top:auto;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
        .ed-feature-footer span{color:#6882a8;font-family:monospace;font-size:11px;letter-spacing:.1em;text-transform:uppercase}
        .ed-stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:22px}
        .ed-stat-card{padding:18px 20px;border-radius:18px;background:rgba(4,10,22,.7);border:1px solid rgba(56,189,248,.1);animation:edUp .45s ease both .12s;transition:border-color .22s ease,transform .22s ease}
        .ed-stat-card:hover{border-color:rgba(56,189,248,.22);transform:translateY(-2px)}
        .ed-stat-card span{display:block;color:#6882a8;font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}
        .ed-stat-card strong{color:#fff;font-size:16px}
        .ed-stat-card strong.green{color:#10fbc4}
        .ed-stat-card strong.amber{color:#fbbf24}
        @media(max-width:980px){.ed-top-row{flex-direction:column;align-items:flex-start}.ed-main-grid,.ed-stats-grid{grid-template-columns:1fr}}
      `}</style>
    </PageWrapper>
  );
}

export default EmployeeDashboardPage;