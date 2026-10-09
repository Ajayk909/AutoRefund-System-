import { useEffect, useState } from "react";
import StaffLayout from "../../components/StaffLayout";
import Dialog from "../../components/Dialog";
import EvidenceImage from "../../components/EvidenceImage";
import VerificationSignals from "../../components/VerificationSignals";
import { CameraIcon, CheckIcon, RefreshIcon } from "../../components/Icons";
import useStaffGuard from "../../hooks/useStaffGuard";
import api, { errorMessage } from "../../services/api";
import { fullDateTime, minutesSince, money, parseServerDate, timeOfDay } from "../../services/format";

function QueueCard({ item, selected, onSelect }) {
  return (
    <li>
      <button className={`s-card s-queue-card ${selected ? "s-queue-card-selected" : ""}`} onClick={() => onSelect(item.refund_id)}>
        <span className="s-queue-name">{item.item_name}</span>
        <span className="s-queue-reason">{item.decision_reason || "No reason was recorded."}</span>
        <span className="s-queue-meta">{item.kiosk_code} · {timeOfDay(parseServerDate(item.refund_date))}</span>
      </button>
    </li>
  );
}

function Fact({ label, children }) {
  return <div className="s-fact"><dt>{label}</dt><dd>{children}</dd></div>;
}

function RefundDetail({ item, busy, actionError, onApprove, onReject }) {
  return (
    <section className="s-card s-detail">
      <h2 className="s-detail-name">{item.item_name}</h2>
      <p className="s-detail-sub">Refund #{item.refund_id.slice(0, 8)} · {fullDateTime(parseServerDate(item.refund_date))}</p>

      <div className="s-flagged">
        <div className="s-flagged-label">Flagged because</div>
        <div>{item.decision_reason || "No reason was recorded."}</div>
      </div>

      <div className="s-detail-body">
        <div>
          <div className="s-photo">
            {item.image_url
              ? <EvidenceImage url={item.image_url} className="s-photo-img" />
              : <span className="s-photo-none"><CameraIcon size={36} stroke={1.5} />No photo was captured for this return</span>}
          </div>
          {item.image_url && <div className="s-photo-caption">Photo from the kiosk</div>}
        </div>
        <dl className="s-facts">
          <Fact label="Measured">{item.measured_weight_grams} g</Fact>
          <Fact label="Expected">{item.expected_weight_grams ?? "—"} g</Fact>
          <Fact label="Amount">{money(item.refund_amount)}</Fact>
          <Fact label="Quantity">{item.quantity}</Fact>
          <Fact label="Barcode">{item.barcode || "—"}</Fact>
          <Fact label="Store · Kiosk">{item.store_code} · {item.kiosk_code}</Fact>
        </dl>
      </div>

      <VerificationSignals signals={item.verification_signals} />

      {actionError && <div className="s-error" role="alert">{actionError}</div>}
      <div className="s-detail-footer">
        <p>Approving doesn't move money. Refund at the POS, then mark it refunded in the Return log.</p>
        <button className="s-btn s-btn-danger-outline" disabled={busy} onClick={onReject}>Reject</button>
        <button className="s-btn s-btn-primary" disabled={busy} onClick={onApprove}>{busy ? "Saving…" : "Approve"}</button>
      </div>
    </section>
  );
}

function PendingRefundsPage() {
  useStaffGuard();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [rejecting, setRejecting] = useState(false); // reject dialog open?
  const [reason, setReason] = useState("");

  const load = async () => {
    try {
      setLoading(true); setLoadError("");
      const r = await api.get("/refunds/pending");
      setItems(r.data.refunds || []);
    } catch { setLoadError("Could not load the review queue. Please try again."); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  // Show the chosen return, or the first one when nothing (or a gone one) is chosen.
  const selected = items.find((i) => i.refund_id === selectedId) || items[0];

  const decide = async (action, body) => {
    try { setBusy(true); setActionError(""); await api.post(`/refunds/${selected.refund_id}/${action}`, body); }
    catch (err) { setActionError(errorMessage(err, `Failed to ${action}.`)); }
    finally { setBusy(false); await load(); }
  };

  const confirmReject = () => {
    setRejecting(false);
    decide("reject", { reason });
  };

  const oldest = items.length ? minutesSince(parseServerDate(items[items.length - 1].refund_date)) : 0; // newest first
  const summary = items.length === 0
    ? "Nothing waiting"
    : `${items.length} ${items.length === 1 ? "return" : "returns"} waiting · oldest waiting ${oldest} min`;

  return (
    <StaffLayout pendingCount={loading ? undefined : items.length}>
      <div className="s-page-head">
        <div>
          <h1 className="s-title">Review queue</h1>
          <p className="s-subtitle">{loading ? "Loading…" : summary}</p>
        </div>
        <button className="s-btn s-btn-secondary s-refresh" onClick={load} disabled={loading}>
          <RefreshIcon size={18} stroke={2} /> {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {loadError && <div className="s-error s-error-page" role="alert">{loadError}</div>}

      {!loading && items.length === 0 ? (
        <div className="s-card s-empty">
          <span className="s-empty-icon"><CheckIcon size={32} stroke={2} /></span>
          <h2>The queue is clear</h2>
          <p className="s-muted">No returns are waiting for review.</p>
        </div>
      ) : selected && (
        <div className="s-queue">
          <ul className="s-queue-list">
            {items.map((item) => (
              <QueueCard key={item.refund_id} item={item} selected={item === selected}
                onSelect={(id) => { setSelectedId(id); setActionError(""); }} />
            ))}
          </ul>
          <RefundDetail item={selected} busy={busy} actionError={actionError}
            onApprove={() => decide("approve")}
            onReject={() => { setReason(""); setRejecting(true); }} />
        </div>
      )}

      {rejecting && (
        <Dialog
          title="Reject this return?"
          actions={
            <>
              <button className="s-btn s-btn-secondary" onClick={() => setRejecting(false)}>Cancel</button>
              <button className="s-btn s-btn-danger" onClick={confirmReject}>Reject return</button>
            </>
          }
        >
          <p className="dialog-text">Write a short reason. It's saved in the audit log.</p>
          <textarea className="s-input s-textarea" value={reason} onChange={(e) => setReason(e.target.value)} autoFocus />
        </Dialog>
      )}
    </StaffLayout>
  );
}

export default PendingRefundsPage;
