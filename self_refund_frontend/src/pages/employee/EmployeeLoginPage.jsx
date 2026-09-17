import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";
import api from "../../services/api";
import { saveStaffSession } from "../../services/staffSession";

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

function EmployeeLoginPage() {
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!employeeId.trim() || !password.trim()) { setError("Please enter both Employee ID and password."); return; }
    try {
      setLoading(true); setError("");
      const res = await api.post("/staff/login", { username: employeeId, password });
      saveStaffSession(res.data.token, res.data.staff);
      navigate("/employee/dashboard");
    } catch (err) {
      setError(err?.response?.status === 429
        ? err.response.data.message
        : "Invalid credentials. Please try again.");
    }
    finally { setLoading(false); }
  };

  return (
    <PageWrapper>
      <KioskShell />
      <Layout title="" subtitle="">
        <div className="kiosk-content el-page">
          <div className="el-main-grid">
            <section className="el-visual-panel">
              <div className="el-orb" />
              <div className="el-eyebrow">Secure Staff Access</div>
              <h1 className="page-title" style={{ textAlign: "left", margin: 0 }}>Employee Portal</h1>
              <p className="page-subtitle" style={{ textAlign: "left", margin: 0 }}>
                Sign in to review refund activity, approve pending requests, and access the refund logs dashboard.
              </p>
              <div className="el-feature-stack">
                {[
                  { icon: "⏳", title: "Pending queue", desc: "Approve or reject flagged refunds" },
                  { icon: "📊", title: "Logs access", desc: "Track refund history with date filters" },
                  { icon: "🛡️", title: "Protected entry", desc: "Restricted to authorized staff only" },
                ].map((f, i) => (
                  <div key={i} className="el-feature-card">
                    <span>{f.icon}</span>
                    <div><strong>{f.title}</strong><p>{f.desc}</p></div>
                  </div>
                ))}
              </div>
              <button className="ghost-btn" style={{ width: "fit-content", marginTop: 8 }} onClick={() => navigate("/")}>← Back to Home</button>
            </section>

            <section className="el-form-panel">
              <div className="el-form-head">
                <div className="el-badge">Staff Login</div>
                <h2>Welcome back</h2>
                <p>Enter your employee credentials to continue.</p>
              </div>
              <div className="form-group">
                <label>Employee ID</label>
                <input type="text" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleLogin()} placeholder="Enter your employee ID" autoFocus />
              </div>
              <div className="form-group">
                <label>Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleLogin()} placeholder="Enter your password" />
              </div>
              {error && <div className="error-box">{error}</div>}
              <div className="el-mini-row">
                <div className="el-mini-card"><span>Status</span><strong>{loading ? "Signing in…" : "Ready"}</strong></div>
                <div className="el-mini-card"><span>Portal</span><strong>Employee</strong></div>
              </div>
              <div className="btn-row">
                <button className="ghost-btn" onClick={() => navigate("/")}>← Back</button>
                <button className="primary-btn" onClick={handleLogin} disabled={loading}>{loading ? "Signing in…" : "Sign In →"}</button>
              </div>
            </section>
          </div>
        </div>
      </Layout>

      <style>{`
        @keyframes elUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
        @keyframes elFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-12px)}}
        .el-page{min-height:calc(100vh - 110px)}
        .el-main-grid{display:grid;grid-template-columns:minmax(340px,1.05fr) minmax(380px,.95fr);gap:32px;align-items:stretch;min-height:calc(100vh - 180px)}
        .el-visual-panel,.el-form-panel{animation:elUp .45s ease both}
        .el-visual-panel{position:relative;overflow:hidden;border-radius:28px;padding:36px;background:linear-gradient(180deg,rgba(8,16,36,.9),rgba(4,10,22,.82));border:1px solid rgba(56,189,248,.15);display:flex;flex-direction:column;justify-content:center;gap:20px;box-shadow:0 0 40px rgba(56,189,248,.06)}
        .el-orb{position:absolute;width:280px;height:280px;right:-70px;top:-40px;border-radius:50%;background:radial-gradient(circle,rgba(56,189,248,.22),rgba(56,189,248,0) 70%);animation:elFloat 4s ease-in-out infinite;pointer-events:none}
        .el-eyebrow{display:inline-flex;width:fit-content;padding:7px 12px;border-radius:999px;background:rgba(16,251,196,.1);border:1px solid rgba(16,251,196,.22);color:#10fbc4;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}
        .el-feature-stack{display:grid;gap:12px;margin-top:8px}
        .el-feature-card{display:flex;gap:14px;align-items:flex-start;padding:16px 18px;border-radius:18px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);transition:border-color .22s ease,transform .22s ease}
        .el-feature-card:hover{border-color:rgba(56,189,248,.2);transform:translateX(4px)}
        .el-feature-card span{font-size:24px;flex-shrink:0;margin-top:2px}
        .el-feature-card strong{display:block;color:#fff;margin-bottom:4px;font-size:15px}
        .el-feature-card p{color:#9db0ce;line-height:1.6;font-size:13px}
        .el-form-panel{padding:32px;border-radius:28px;background:rgba(8,16,36,.95);border:1px solid rgba(56,189,248,.15);display:flex;flex-direction:column;justify-content:center;gap:18px;box-shadow:0 0 40px rgba(56,189,248,.07)}
        .el-badge{display:inline-flex;width:fit-content;padding:7px 12px;border-radius:999px;background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.22);color:#8ddcff;font-size:12px;font-weight:700;margin-bottom:10px}
        .el-form-head h2{font-size:32px;color:#fff;margin-bottom:6px}
        .el-form-head p{color:#9db0ce;line-height:1.7}
        .el-mini-row{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
        .el-mini-card{padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07)}
        .el-mini-card span{display:block;color:#6882a8;font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px}
        .el-mini-card strong{color:#fff}
        @media(max-width:980px){.el-main-grid{grid-template-columns:1fr;min-height:auto}}
        @media(max-width:600px){.el-mini-row{grid-template-columns:1fr}.el-visual-panel,.el-form-panel{padding:24px}}
      `}</style>
    </PageWrapper>
  );
}

export default EmployeeLoginPage;