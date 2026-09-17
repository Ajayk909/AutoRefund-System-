// PendingRefundsPage.jsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";
import api, { captureUrl } from "../../services/api";

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

function PendingRefundsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoad, setActionLoad] = useState("");

  const load = async () => {
    try { setLoading(true); const r = await api.get("/refunds/pending"); setItems(r.data.refunds || []); }
    catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleApprove = async (id) => {
    try { setActionLoad(`${id}-a`); await api.post(`/refunds/${id}/approve`); await load(); }
    catch { alert("Failed to approve."); } finally { setActionLoad(""); }
  };

  const handleReject = async (id) => {
    try { setActionLoad(`${id}-r`); await api.post(`/refunds/${id}/reject`); await load(); }
    catch { alert("Failed to reject."); } finally { setActionLoad(""); }
  };

  return (
    <PageWrapper>
      <KioskShell />
      <Layout title="" subtitle="">
        <div className="kiosk-content pr-page">
          <div className="pr-top-row">
            <div className="kiosk-hero pr-hero" style={{ textAlign: "left", padding: "32px 0 24px" }}>
              <div className="kiosk-eyebrow">Employee Dashboard</div>
              <h1 className="page-title">Pending Refunds</h1>
              <p className="page-subtitle">Review refund requests that need manual action. Approve or reject each one directly.</p>
            </div>
            <div className="pr-top-actions">
              <button className="ghost-btn" onClick={() => navigate("/employee/dashboard")}>← Dashboard</button>
              <button className="ghost-btn" onClick={load}>{loading ? "Refreshing…" : "🔄 Refresh"}</button>
            </div>
          </div>

          <div className="pr-stats-row">
            <div className="pr-stat-card"><span>Queue</span><strong>{loading ? "..." : items.length}</strong></div>
            <div className="pr-stat-card"><span>Status</span><strong className="amber">Manual Review</strong></div>
            <div className="pr-stat-card"><span>Actions</span><strong>Approve / Reject</strong></div>
          </div>

          {loading ? (
            <div className="pr-empty"><div className="pr-empty-icon">⟳</div><p>Loading pending refunds…</p></div>
          ) : items.length === 0 ? (
            <div className="pr-empty">
              <div className="pr-empty-icon" style={{ color: "#10fbc4" }}>✓</div>
              <h3 style={{ color: "#10fbc4", fontFamily: "'Orbitron',sans-serif", fontSize: 20 }}>Queue is clear!</h3>
              <p>No pending refunds. All requests have been processed.</p>
              <button className="ghost-btn" onClick={() => navigate("/employee/dashboard")}>← Back to Dashboard</button>
            </div>
          ) : (
            <div className="pr-list">
              {items.map((item, index) => (
                <div className="pr-card" key={item.refund_id} style={{ animationDelay: `${0.06 + index * 0.04}s` }}>
                  <div className="pr-card-head">
                    <div>
                      <div className="pr-card-name">{item.item_name}</div>
                      <div className="pr-card-sub">Refund #{item.refund_id}</div>
                    </div>
                    <span className="pr-badge">Pending</span>
                  </div>
                  <div className="pr-card-body">
                    <div className="pr-field"><span className="pr-label">Measured</span><span className="pr-val pr-mono">{item.measured_weight_grams} g</span></div>
                    <div className="pr-field"><span className="pr-label">Expected</span><span className="pr-val pr-mono">{item.expected_weight_grams} g</span></div>
                    <div className="pr-field"><span className="pr-label">Amount</span><span className="pr-val pr-amount">${item.refund_amount}</span></div>
                    <div className="pr-field"><span className="pr-label">Date</span><span className="pr-val">{item.refund_date ? new Date(item.refund_date).toLocaleString() : "N/A"}</span></div>
                  </div>
                  {item.image_path && (
                    <div className="pr-image-preview">
                      <div className="pr-image-label">Captured Image</div>
                      <img src={captureUrl(item.image_path)} alt="Captured item" className="pr-image-thumb" onError={e => { e.target.style.display = "none"; }} />
                    </div>
                  )}
                  <div className="btn-row pr-actions">
                    <button className="ghost-btn" onClick={() => navigate("/employee/dashboard")}>← Dashboard</button>
                    <div className="pr-action-buttons">
                      <button className="reject-btn" disabled={actionLoad === `${item.refund_id}-r`} onClick={() => handleReject(item.refund_id)}>{actionLoad === `${item.refund_id}-r` ? "Rejecting…" : "✗ Reject"}</button>
                      <button className="approve-btn" disabled={actionLoad === `${item.refund_id}-a`} onClick={() => handleApprove(item.refund_id)}>{actionLoad === `${item.refund_id}-a` ? "Approving…" : "✓ Approve"}</button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Layout>

      <style>{`
        @keyframes prUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
        .pr-page{min-height:calc(100vh - 110px)}
        .pr-top-row{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:16px}
        .pr-top-actions{display:flex;gap:12px;flex-wrap:wrap}
        .pr-stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:18px}
        .pr-stat-card{padding:18px 20px;border-radius:18px;background:rgba(4,10,22,.72);border:1px solid rgba(56,189,248,.1);transition:border-color .22s,transform .22s}
        .pr-stat-card:hover{border-color:rgba(56,189,248,.22);transform:translateY(-2px)}
        .pr-stat-card span{display:block;color:#6882a8;font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}
        .pr-stat-card strong{color:#fff;font-size:16px}
        .pr-stat-card strong.amber{color:#fbbf24}
        .pr-empty{min-height:280px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;border-radius:24px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);padding:40px}
        .pr-empty-icon{font-size:48px}
        .pr-empty p{color:#9db0ce;font-size:16px}
        .pr-list{display:grid;gap:16px}
        .pr-card{padding:26px;border-radius:24px;background:rgba(8,16,36,.95);border:1px solid rgba(56,189,248,.14);animation:prUp .4s ease both;transition:transform .22s ease,border-color .22s ease,box-shadow .22s ease}
        .pr-card:hover{transform:translateY(-3px);border-color:rgba(56,189,248,.26);box-shadow:0 16px 42px rgba(0,0,0,.25)}
        .pr-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid rgba(56,189,248,.1)}
        .pr-card-name{font-size:22px;color:#fff;font-weight:700}
        .pr-card-sub{color:#6882a8;font-size:13px;margin-top:6px}
        .pr-badge{padding:5px 12px;border-radius:999px;font-family:monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;border:1px solid rgba(251,191,36,.28);background:rgba(251,191,36,.12);color:#fbbf24;font-weight:700}
        .pr-card-body{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
        .pr-field{padding:14px 16px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07)}
        .pr-label{display:block;color:#6882a8;font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}
        .pr-val{color:#fff}
        .pr-val.pr-mono{font-family:monospace;color:#8ddcff}
        .pr-val.pr-amount{color:#10fbc4;font-size:22px;font-weight:800}
        .pr-actions{justify-content:space-between}
        .pr-action-buttons{display:flex;gap:10px;flex-wrap:wrap}
        .pr-image-preview{margin-bottom:12px;padding:14px;border-radius:12px;background:rgba(4,10,22,.6);border:1px solid rgba(56,189,248,.12)}
        .pr-image-label{font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#4e6587;margin-bottom:10px}
        .pr-image-thumb{width:100%;max-height:200px;object-fit:contain;border-radius:8px;border:1px solid rgba(56,189,248,.18);background:rgba(2,8,16,.8)}
        @media(max-width:980px){.pr-top-row{flex-direction:column;align-items:flex-start}.pr-stats-row,.pr-card-body{grid-template-columns:1fr 1fr}}
        @media(max-width:600px){.pr-stats-row,.pr-card-body{grid-template-columns:1fr}.pr-card-head{flex-direction:column}.pr-actions{flex-direction:column;align-items:stretch}.pr-action-buttons{width:100%}.pr-action-buttons button{flex:1}}
      `}</style>
    </PageWrapper>
  );
}

export default PendingRefundsPage;