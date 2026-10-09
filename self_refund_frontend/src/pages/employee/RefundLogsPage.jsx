import { useEffect, useState } from "react";
import StaffLayout from "../../components/StaffLayout";
import Dialog from "../../components/Dialog";
import StatusPill from "../../components/StatusPill";
import EvidenceImage from "../../components/EvidenceImage";
import VerificationSignals from "../../components/VerificationSignals";
import { CameraIcon, ChevronDownIcon, ChevronUpIcon, RefreshIcon } from "../../components/Icons";
import useStaffGuard from "../../hooks/useStaffGuard";
import api, { errorMessage } from "../../services/api";
import { dayAndTime, money, parseServerDate } from "../../services/format";
import { decidedBy, statusInfo } from "./refundStatus";

// The details under a row when it is opened.
function LogDetails({ log, onMarkRefunded }) {
  // A rejection with no staff member was decided by the kiosk itself.
  const kioskDecline = log.decision_status === "rejected" && !log.reviewed_by;
  return (
    <div className="s-log-details">
      <div className="s-log-photo">
        {log.image_url
          ? <EvidenceImage url={log.image_url} className="s-photo-img" />
          : <span className="s-photo-none"><CameraIcon size={28} stroke={1.5} />No photo</span>}
      </div>
      <div className="s-log-info">
        <dl>
          <dt>Amount</dt><dd>{money(log.refund_amount)} (qty {log.quantity})</dd>
          <dt>Weight</dt><dd>{log.measured_weight_grams} g (expected {log.expected_weight_grams ?? "—"} g)</dd>
          <dt>Reason</dt><dd>{log.decision_reason || "—"}</dd>
          {log.reviewed_by && <><dt>Reviewed by</dt><dd>{log.reviewed_by}</dd></>}
          {log.payment_reference && <><dt>POS ref</dt><dd>{log.payment_reference}</dd></>}
        </dl>
        {kioskDecline && <VerificationSignals signals={log.verification_signals} />}
      </div>
      {log.decision_status === "approved" && (
        <button className="s-btn s-btn-primary s-log-mark" onClick={(e) => { e.stopPropagation(); onMarkRefunded(log); }}>
          Mark refunded at POS
        </button>
      )}
    </div>
  );
}

function RefundLogsPage() {
  useStaffGuard();
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [startDate, setStart] = useState("");
  const [endDate, setEnd] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [marking, setMarking] = useState(null); // the row in the "Mark as refunded" dialog
  const [reference, setReference] = useState("");
  const [markError, setMarkError] = useState("");

  const load = async (sd = startDate, ed = endDate) => {
    try {
      setLoading(true); setLoadError("");
      let url = "/refunds/logs";
      const params = [];
      if (sd) params.push(`start_date=${sd}`);
      if (ed) params.push(`end_date=${ed}`);
      if (params.length) url += `?${params.join("&")}`;
      const r = await api.get(url);
      setLogs(r.data.refunds || []);
    } catch { setLoadError("Failed to load refund logs."); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const handleClear = () => { setStart(""); setEnd(""); load("", ""); };

  const approvedCount = logs.filter((log) => log.decision_status === "approved").length;
  const pendingCount = logs.filter((log) => log.decision_status === "pending_review").length;

  const openMarkDialog = (log) => { setMarking(log); setReference(""); setMarkError(""); };

  // "Approved" does not move money. Staff issue the refund at the POS and
  // record its reference here (approved -> refunded).
  const markRefunded = async () => {
    try {
      await api.post(`/refunds/${marking.refund_id}/mark-refunded`, { payment_reference: reference.trim() });
      setMarking(null);
      await load();
    } catch (err) { setMarkError(errorMessage(err, "Could not record the refund.")); }
  };

  return (
    <StaffLayout>
      <div className="s-page-head">
        <div>
          <h1 className="s-title">Return log</h1>
          <p className="s-subtitle">Every return from this store, newest first.</p>
        </div>
        <button className="s-btn s-btn-secondary s-refresh" onClick={() => load()} disabled={loading}>
          <RefreshIcon size={18} stroke={2} /> {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="s-card s-filter">
        <label className="s-filter-field">
          <span className="s-label">From</span>
          <input className="s-input s-date" type="date" value={startDate} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="s-filter-field">
          <span className="s-label">To</span>
          <input className="s-input s-date" type="date" value={endDate} onChange={(e) => setEnd(e.target.value)} />
        </label>
        <button className="s-btn s-btn-primary" onClick={() => load()}>Apply</button>
        <button className="s-btn s-btn-secondary" onClick={handleClear}>Clear</button>
        <p className="s-filter-counts">
          <strong>{logs.length}</strong> returns
          <strong className="s-success">{approvedCount}</strong> approved
          <strong className="s-review">{pendingCount}</strong> waiting for review
        </p>
      </div>

      {loadError && <div className="s-error s-error-page" role="alert">{loadError}</div>}

      <section className="s-card s-table">
        <div className="s-table-row s-table-head">
          <span>Item</span><span>Status</span><span>Decided by</span><span>Date &amp; time</span><span />
        </div>
        <div className="s-table-body">
          {loading ? (
            <p className="s-muted s-table-empty">Loading refund logs…</p>
          ) : logs.length === 0 ? (
            <p className="s-muted s-table-empty">No returns found for these dates.</p>
          ) : logs.map((log) => {
            const open = expanded === log.refund_id;
            const status = statusInfo(log);
            return (
              <div key={log.refund_id} className={`s-log ${open ? "s-log-open" : ""}`}>
                <button className="s-table-row" onClick={() => setExpanded(open ? null : log.refund_id)} aria-expanded={open}>
                  <span className="s-table-item">{log.item_name}</span>
                  <span><StatusPill tone={status.tone}>{status.word}</StatusPill></span>
                  <span className="s-muted">{decidedBy(log)}</span>
                  <span className="s-muted">{dayAndTime(parseServerDate(log.refund_date))}</span>
                  <span className="s-chevron">{open ? <ChevronUpIcon size={20} /> : <ChevronDownIcon size={20} />}</span>
                </button>
                {open && <LogDetails log={log} onMarkRefunded={openMarkDialog} />}
              </div>
            );
          })}
        </div>
      </section>

      {marking && (
        <Dialog
          title="Mark as refunded"
          className="s-dialog-narrow"
          actions={
            <>
              <button className="s-btn s-btn-secondary" onClick={() => setMarking(null)}>Cancel</button>
              <button className="s-btn s-btn-primary" onClick={markRefunded} disabled={!reference.trim()}>Mark refunded</button>
            </>
          }
        >
          <p className="dialog-text">
            Enter the refund reference number from the POS receipt. {marking.item_name} · {money(marking.refund_amount)}
          </p>
          <label className="s-label" htmlFor="pos-ref">POS refund reference</label>
          <input id="pos-ref" className="s-input" value={reference} onChange={(e) => setReference(e.target.value)} autoFocus />
          {markError && <div className="s-error" role="alert">{markError}</div>}
        </Dialog>
      )}
    </StaffLayout>
  );
}

export default RefundLogsPage;
