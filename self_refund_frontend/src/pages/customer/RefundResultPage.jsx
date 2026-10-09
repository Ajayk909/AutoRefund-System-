import { useState } from "react";
import { useNavigate } from "react-router-dom";
import KioskLayout from "../../components/KioskLayout";
import { ItemSummary } from "../../components/ItemSummary";
import StatusPill from "../../components/StatusPill";
import { AlertIcon, CheckIcon, UserIcon } from "../../components/Icons";
import { resetAndGoHome } from "../../services/kioskSession";
import { money } from "../../services/format";

function readSaved(key) {
  const saved = localStorage.getItem(key);
  return saved ? JSON.parse(saved) : null;
}

// What the customer sees for each decision_status from the server.
function resultView(result) {
  if (result.decision_status === "approved") {
    return {
      tone: "success", topTitle: "Return complete", icon: <CheckIcon size={70} stroke={2} />,
      headline: "Your refund is approved",
      text: `Your refund of ${money(result.refund_amount)} will go back to your original payment.`,
      status: "Approved", refundLabel: "Refund", refund: money(result.refund_amount),
    };
  }
  // "rejected" here means the kiosk declined the return itself (e.g. weight far off).
  if (result.decision_status === "rejected") {
    return {
      tone: "decline", topTitle: "Return not completed", icon: <AlertIcon size={69} stroke={2} />,
      headline: "We can't complete this return here",
      text: result.decision_reason,
      note: "Nothing has been refunded. Please take the item and your receipt to the customer service desk.",
      status: "Not completed", refundLabel: "Refund", refund: "None",
    };
  }
  return {
    tone: "review", topTitle: "Almost done", icon: <UserIcon size={65} stroke={2} />,
    headline: "An employee will check this return",
    text: "Your return is saved, so you don't need to scan anything again.",
    note: "An employee will review it. Please wait here, or go to the customer service desk.",
    status: "Waiting for review", refundLabel: "Refund if approved", refund: money(result.refund_amount),
  };
}

function RefundResultPage() {
  // Read the saved return once, when the page opens.
  const [result] = useState(() => readSaved("refundResult"));
  const [item] = useState(() => readSaved("selectedItem"));
  const [transaction] = useState(() => readSaved("transactionData"));
  const navigate = useNavigate();

  if (!result) {
    return (
      <KioskLayout title="Return complete" panelClass="k-panel-roomy">
        <h1 className="k-h1">No result to show</h1>
        <p className="k-lead">Start a new return to scan your receipt.</p>
        <button className="k-btn k-btn-primary k-btn-big k-push-down" onClick={() => navigate("/customer/receipt")}>
          Start a new return
        </button>
      </KioskLayout>
    );
  }

  const view = resultView(result);

  const side = (
    <div className="k-card">
      <h2 className="k-card-title k-card-title-small">Return summary</h2>
      {item && <ItemSummary name={item.name} receiptNumber={transaction?.receipt_number} />}
      <dl className="k-facts k-facts-tight k-facts-result">
        <div><dt>Status</dt><dd><StatusPill tone={view.tone}>{view.status}</StatusPill></dd></div>
        <div><dt>{view.refundLabel}</dt><dd>{view.refund}</dd></div>
      </dl>
    </div>
  );

  return (
    <KioskLayout title={view.topTitle} side={side} panelClass="k-panel-roomy">
      <div className={`k-result-icon k-result-icon-${view.tone}`}>{view.icon}</div>
      <h1 className="k-h1 k-result-headline">{view.headline}</h1>
      <p className="k-lead">{view.text}</p>
      {view.note && <p className="k-result-note">{view.note}</p>}
      <button className="k-btn k-btn-primary k-btn-big k-result-btn" onClick={() => resetAndGoHome(navigate)}>
        Start a new return
      </button>
    </KioskLayout>
  );
}

export default RefundResultPage;
