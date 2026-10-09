import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import StaffLayout from "../../components/StaffLayout";
import StatusPill from "../../components/StatusPill";
import { InboxIcon, ListIcon } from "../../components/Icons";
import useStaffGuard from "../../hooks/useStaffGuard";
import api from "../../services/api";
import { isToday, minutesSince, parseServerDate, timeOfDay } from "../../services/format";
import { decidedBy, statusInfo } from "./refundStatus";

// The four numbers at the top, counted from the queue and the full log.
function countStats(pending, logs) {
  const oldest = pending.length ? parseServerDate(pending[pending.length - 1].refund_date) : null; // newest first
  return {
    waiting: pending.length,
    oldestMinutes: oldest ? minutesSince(oldest) : null,
    approved: logs.filter((r) => r.decision_status === "approved").length,
    refundedToday: logs.filter((r) => isToday(parseServerDate(r.refunded_at))).length,
    // The kiosk decides when the return is made, so refund_date is the decision time.
    declinedToday: logs.filter((r) => r.decision_status === "rejected" && !r.reviewed_by && isToday(parseServerDate(r.refund_date))).length,
  };
}

function StatCard({ label, value, note, tone = "" }) {
  return (
    <div className="s-card s-stat">
      <div className="s-stat-label">{label}</div>
      <div className={`s-stat-value ${tone}`}>{value}</div>
      <div className="s-stat-note">{note}</div>
    </div>
  );
}

function EmployeeDashboardPage() {
  const navigate = useNavigate();
  const staff = useStaffGuard();
  const [pending, setPending] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get("/refunds/pending"), api.get("/refunds/logs")])
      .then(([p, l]) => { setPending(p.data.refunds || []); setLogs(l.data.refunds || []); })
      .catch(() => setError("Could not load the overview. Please refresh the page."))
      .finally(() => setLoading(false));
  }, []);

  const stats = countStats(pending, logs);
  const firstName = (staff.full_name || "").split(" ")[0];
  const show = (n) => (loading ? "…" : n);

  return (
    <StaffLayout pendingCount={loading ? undefined : pending.length}>
      <h1 className="s-title">Welcome back{firstName ? `, ${firstName}` : ""}</h1>
      <p className="s-subtitle">Here's what needs your attention today.</p>
      {error && <div className="s-error s-error-page" role="alert">{error}</div>}

      <div className="s-stats">
        <StatCard label="Waiting for review" value={show(stats.waiting)} tone="s-review"
          note={stats.oldestMinutes === null ? "Nothing waiting" : `Oldest waiting ${stats.oldestMinutes} min`} />
        <StatCard label="Approved, not refunded yet" value={show(stats.approved)} tone="s-primary"
          note="Refund at the POS, then mark it refunded" />
        <StatCard label="Refunded today" value={show(stats.refundedToday)} note="Recorded with a POS reference" />
        <StatCard label="Declined by the kiosk today" value={show(stats.declinedToday)} note="Customer sent to the service desk" />
      </div>

      <div className="s-shortcuts">
        <div className="s-card s-shortcut">
          <span className="s-icon-tile s-icon-tile-big"><InboxIcon size={24} stroke={1.5} /></span>
          <div className="s-shortcut-text">
            <h2>Review queue</h2>
            <p>{stats.waiting === 1 ? "1 return needs a decision." : `${stats.waiting} returns need a decision.`}</p>
          </div>
          <button className="s-btn s-btn-primary" onClick={() => navigate("/employee/pending")}>Open review queue</button>
        </div>
        <div className="s-card s-shortcut">
          <span className="s-icon-tile s-icon-tile-big"><ListIcon size={24} stroke={1.5} /></span>
          <div className="s-shortcut-text">
            <h2>Return log</h2>
            <p>Search past returns by date and record POS refunds.</p>
          </div>
          <button className="s-btn s-btn-secondary" onClick={() => navigate("/employee/logs")}>Open return log</button>
        </div>
      </div>

      <section className="s-card s-latest">
        <div className="s-latest-head">
          <h2>Latest decisions</h2>
          <Link to="/employee/logs" className="s-text-link">See all in Return log</Link>
        </div>
        {loading ? (
          <p className="s-muted s-latest-empty">Loading…</p>
        ) : logs.length === 0 ? (
          <p className="s-muted s-latest-empty">No returns yet.</p>
        ) : (
          <ul className="s-latest-list">
            {logs.slice(0, 4).map((row) => {
              const status = statusInfo(row);
              return (
                <li key={row.refund_id}>
                  <span className="s-latest-item">{row.item_name}</span>
                  <span><StatusPill tone={status.tone}>{status.word}</StatusPill></span>
                  <span className="s-muted">{decidedBy(row)}</span>
                  <span className="s-muted s-latest-time">{timeOfDay(parseServerDate(row.refund_date))}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </StaffLayout>
  );
}

export default EmployeeDashboardPage;
