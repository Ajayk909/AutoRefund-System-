import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";
import api, { errorMessage } from "../../services/api";
import EvidenceImage from "../../components/EvidenceImage";
import useStaffGuard from "../../hooks/useStaffGuard";

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

const statusClass = (status) => {
  if (!status) return "neutral";
  const lower = status.toLowerCase();
  if (lower === "approved") return "approved";
  if (lower === "rejected") return "rejected";
  if (lower === "refunded") return "approved";
  return "pending";
};

function RefundLogsPage() {
  const navigate = useNavigate();
  useStaffGuard();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [startDate, setStart] = useState("");
  const [endDate, setEnd] = useState("");
  const [expanded, setExpanded] = useState(null);

  const load = async (sd = startDate, ed = endDate) => {
    try {
      setLoading(true);
      let url = "/refunds/logs";
      const params = [];
      if (sd) params.push(`start_date=${sd}`);
      if (ed) params.push(`end_date=${ed}`);
      if (params.length) url += `?${params.join("&")}`;
      const r = await api.get(url);
      setLogs(r.data.refunds || []);
    } catch (e) { console.error(e); alert("Failed to load refund logs."); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleClear = () => { setStart(""); setEnd(""); setTimeout(() => load("", ""), 0); };

  const approvedCount = logs.filter((log) => log.decision_status?.toLowerCase() === "approved").length;
  const pendingCount = logs.filter((log) => log.decision_status?.toLowerCase() === "pending_review").length;

  // "Approved" does not move money. Staff issue the refund at the POS and
  // record its reference here (approved -> refunded).
  const markRefunded = async (id) => {
    const reference = window.prompt("Enter the POS refund reference number:", "");
    if (!reference) return;
    try { await api.post(`/refunds/${id}/mark-refunded`, { payment_reference: reference }); await load(); }
    catch (err) { alert(errorMessage(err, "Could not record the refund.")); }
  };

  return (
    <PageWrapper>
      <KioskShell />
      <Layout title="" subtitle="">
        <div className="kiosk-content rl-page">
          <div className="rl-top-row">
            <div className="kiosk-hero" style={{ textAlign: "left", padding: "32px 0 24px" }}>
              <div className="kiosk-eyebrow">Employee Dashboard</div>
              <h1 className="page-title">Refund Logs</h1>
              <p className="page-subtitle">Review refund history, check statuses, and narrow results by date range.</p>
            </div>
            <div className="rl-top-actions">
              <button className="ghost-btn" onClick={() => navigate("/employee/dashboard")}>← Dashboard</button>
              <button className="ghost-btn" onClick={() => load()}>{loading ? "Refreshing…" : "🔄 Refresh"}</button>
            </div>
          </div>

          <div className="rl-stats-row">
            <div className="rl-stat-card"><span>Total</span><strong>{loading ? "..." : logs.length}</strong></div>
            <div className="rl-stat-card"><span>Approved</span><strong className="green">{loading ? "..." : approvedCount}</strong></div>
            <div className="rl-stat-card"><span>Pending</span><strong className="amber">{loading ? "..." : pendingCount}</strong></div>
          </div>

          <div className="rl-filter-card">
            <div className="rl-filter-head">
              <div className="rl-badge">Date Filter</div>
              <h2>Filter refund records</h2>
            </div>
            <div className="filter-grid rl-filter-grid">
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>Start Date</label>
                <input type="date" value={startDate} onChange={(e) => setStart(e.target.value)} />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label>End Date</label>
                <input type="date" value={endDate} onChange={(e) => setEnd(e.target.value)} />
              </div>
            </div>
            <div className="btn-row rl-filter-actions">
              <button className="primary-btn" onClick={() => load()}>Apply Filter</button>
              <button className="ghost-btn" onClick={handleClear}>Clear</button>
            </div>
          </div>

          {loading ? (
            <div className="rl-empty"><div className="rl-empty-icon">⟳</div><p>Loading refund logs…</p></div>
          ) : logs.length === 0 ? (
            <div className="rl-empty"><div className="rl-empty-icon">∅</div><p>No records found for the selected range.</p></div>
          ) : (
            <div className="rl-table-wrap">
              <div className="rl-header-row">
                <span>Item Name</span>
                <span>Status</span>
                <span>Decision</span>
                <span style={{ textAlign: "right" }}>Date &amp; Time</span>
              </div>
              <div className="table-list rl-table-list">
                {logs.map((log, i) => (
                  <div key={log.refund_id}>
                    <div
                      className="table-row rl-table-row"
                      style={{ cursor: "pointer", animationDelay: `${i * 0.04}s` }}
                      onClick={() => setExpanded(expanded === log.refund_id ? null : log.refund_id)}
                    >
                      <div><strong>{log.item_name}</strong></div>
                      <div>
                        <span className={`rl-status rl-${statusClass(log.decision_status)}`}>{log.decision_status}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ color: "#c9d8f0", fontSize: 13 }}>{log.refund_date ? new Date(log.refund_date).toLocaleString() : "N/A"}</span>
                        <span style={{ color: "#38bdf8", fontSize: 12 }}>{expanded === log.refund_id ? "▲ Hide" : "▼ Details"}</span>
                      </div>
                    </div>
                    {expanded === log.refund_id && (
                      <div className="rl-image-expand">
                        {log.image_url ? <EvidenceImage url={log.image_url} className="rl-image-full" /> : <div style={{ color: "#6882a8" }}>No photo captured</div>}
                        <div className="rl-image-meta">
                          <span>Amount: ${log.refund_amount} (qty {log.quantity})</span>
                          <span>Weight: {log.measured_weight_grams} g (expected {log.expected_weight_grams} g)</span>
                          <span>Reason: {log.decision_reason || "—"}</span>
                          {log.reviewed_by && <span>Reviewed by: {log.reviewed_by}</span>}
                          {log.payment_reference && <span>POS refund ref: {log.payment_reference}</span>}
                          {log.decision_status === "approved" && (
                            <button className="primary-btn" style={{ width: "fit-content" }} onClick={(e) => { e.stopPropagation(); markRefunded(log.refund_id); }}>Mark refunded at POS</button>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </Layout>

      <style>{`
        @keyframes rlUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
        .rl-page{min-height:calc(100vh - 110px)}
        .rl-top-row{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:16px}
        .rl-top-actions{display:flex;gap:12px;flex-wrap:wrap}
        .rl-stats-row{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:18px}
        .rl-stat-card{padding:18px 20px;border-radius:18px;background:rgba(4,10,22,.72);border:1px solid rgba(56,189,248,.1);transition:border-color .22s,transform .22s}
        .rl-stat-card:hover{border-color:rgba(56,189,248,.22);transform:translateY(-2px)}
        .rl-stat-card span{display:block;color:#6882a8;font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px}
        .rl-stat-card strong{color:#fff;font-size:16px}
        .rl-stat-card strong.green{color:#10fbc4}
        .rl-stat-card strong.amber{color:#fbbf24}
        .rl-filter-card{padding:24px;border-radius:24px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.14);animation:rlUp .42s ease both;margin-bottom:18px}
        .rl-filter-head{margin-bottom:16px}
        .rl-filter-head h2{color:#fff;font-size:26px;margin-top:8px}
        .rl-badge{display:inline-flex;width:fit-content;padding:7px 12px;border-radius:999px;background:rgba(56,189,248,.1);border:1px solid rgba(56,189,248,.22);color:#8ddcff;font-size:12px;font-weight:700}
        .rl-filter-grid{margin-top:0}
        .rl-filter-actions{margin-top:14px}
        .rl-empty{min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;border-radius:24px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);padding:40px}
        .rl-empty-icon{font-size:44px;color:#8ddcff}
        .rl-empty p{color:#9db0ce;font-size:16px}
        .rl-table-wrap{padding:22px;border-radius:24px;background:rgba(8,16,36,.92);border:1px solid rgba(56,189,248,.12);animation:rlUp .42s ease both}
        .rl-header-row{display:grid;grid-template-columns:1.2fr .7fr 1.2fr 1fr;gap:14px;padding:0 12px 12px;border-bottom:1px solid rgba(56,189,248,.1);color:#6882a8;font-family:monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;margin-bottom:10px}
        .rl-table-list{display:grid;gap:10px}
        .rl-table-row{display:grid;grid-template-columns:1.2fr .7fr 1.2fr 1fr;gap:14px;align-items:center;padding:16px 14px;border-radius:16px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);animation:rlUp .32s ease both;transition:all .22s ease}
        .rl-table-row:hover{border-color:rgba(56,189,248,.22);background:rgba(56,189,248,.04);transform:translateX(4px)}
        .rl-table-row strong{color:#fff;font-size:15px}
        .rl-status{display:inline-flex;padding:5px 12px;border-radius:999px;font-family:monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;font-weight:700;border:1px solid transparent}
        .rl-status.approved{background:rgba(16,251,196,.12);color:#10fbc4;border-color:rgba(16,251,196,.25)}
        .rl-status.rejected{background:rgba(255,77,109,.12);color:#ff4d6d;border-color:rgba(255,77,109,.25)}
        .rl-status.pending{background:rgba(251,191,36,.12);color:#fbbf24;border-color:rgba(251,191,36,.25)}
        .rl-status.neutral{background:rgba(148,168,199,.1);color:#94a8c7;border-color:rgba(148,168,199,.18)}
        .rl-image-expand{margin:-6px 0 8px;padding:16px 20px 18px;border-radius:0 0 14px 14px;background:rgba(4,10,22,.75);border:1px solid rgba(56,189,248,.12);border-top:none;animation:rlUp .3s ease both}
        .rl-image-full{width:100%;max-height:280px;object-fit:contain;border-radius:10px;border:1px solid rgba(56,189,248,.18);background:rgba(2,8,16,.85);margin-bottom:12px}
        .rl-image-meta{display:flex;gap:24px;font-family:monospace;font-size:11px;color:#4e6587;flex-wrap:wrap}
        @media(max-width:980px){.rl-top-row{flex-direction:column;align-items:flex-start}.rl-stats-row,.rl-header-row,.rl-table-row{grid-template-columns:1fr}.rl-header-row{display:none}}
        @media(max-width:600px){.rl-stats-row{grid-template-columns:1fr}}
      `}</style>
    </PageWrapper>
  );
}

export default RefundLogsPage;