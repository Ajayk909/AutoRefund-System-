import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import KioskLayout from "../../components/KioskLayout";
import { ItemThumb } from "../../components/ItemSummary";
import { InfoIcon, ReceiptIcon } from "../../components/Icons";
import agent from "../../services/agent";
import { money, parseServerDate } from "../../services/format";

const INELIGIBLE_TEXT = {
  ALREADY_RETURNED: "Already returned",
  PENDING_REVIEW: "Waiting for an employee to review",
  OUTSIDE_RETURN_WINDOW: "Outside the return period. Please visit customer service.",
  TOO_MANY_ATTEMPTS: "Please visit customer service for help with this item",
};

// "Beverage · 1 bought", or "Beverage · 2 of 3 can be returned"
function itemDetails(item) {
  const amount = item.quantity > 1 && item.returnable_quantity !== undefined
    ? `${item.returnable_quantity} of ${item.quantity} can be returned`
    : `${item.quantity} bought`;
  return item.category ? `${item.category} · ${amount}` : amount;
}

function ItemRow({ item, onReturn }) {
  const canReturn = item.is_refundable;
  return (
    <li className={`k-item ${canReturn ? "" : "k-item-off"}`}>
      <ItemThumb size={112} />
      <div className="k-item-text">
        <div className="k-item-name">{item.name}</div>
        <div className="k-item-details">{itemDetails(item)}</div>
      </div>
      <div className="k-item-price">{money(item.price_at_purchase)}</div>
      {canReturn ? (
        <button className="k-btn k-btn-outline k-item-btn" onClick={() => onReturn(item)}>Return this</button>
      ) : (
        <span className={`k-item-tag ${item.ineligible_reason === "PENDING_REVIEW" ? "k-item-tag-review" : ""}`}>
          {INELIGIBLE_TEXT[item.ineligible_reason] || "This item can't be returned here"}
        </span>
      )}
    </li>
  );
}

function ItemSelectionPage() {
  const [transaction, setTransaction] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const stored = localStorage.getItem("transactionData");
    if (!stored) return;
    const parsed = JSON.parse(stored);
    const show = (data) => setTransaction({ ...data, items: Array.isArray(data.items) ? data.items : [] });
    show(parsed);
    // Refresh eligibility from the server (another return may have happened).
    agent.get(`/transactions/${encodeURIComponent(parsed.receipt_number)}`)
      .then((res) => {
        localStorage.setItem("transactionData", JSON.stringify(res.data.transaction));
        show(res.data.transaction);
      })
      .catch(() => { /* keep the cached receipt; the server re-checks on submit */ });
  }, []);

  // One tap selects the item and moves on to weighing it.
  const handleReturn = (item) => {
    if (!item.is_refundable) return;
    localStorage.setItem("selectedItem", JSON.stringify(item));
    navigate("/customer/verify");
  };

  const goBack = () => navigate("/customer/receipt");

  if (!transaction) {
    return (
      <KioskLayout title="Choose an item" onBack={goBack} showCancel>
        <h1 className="k-h1">No receipt found</h1>
        <p className="k-lead">Please scan or enter your receipt first.</p>
        <button className="k-btn k-btn-primary k-btn-big k-push-down" onClick={goBack}>Scan your receipt</button>
      </KioskLayout>
    );
  }

  const returnableCount = transaction.items.filter((item) => item.is_refundable).length;

  const side = (
    <>
      <div className="k-card k-card-roomy">
        <div className="k-receipt-head">
          <span className="k-receipt-icon"><ReceiptIcon size={34} /></span>
          <div>
            <div className="k-receipt-head-label">Your receipt</div>
            <div className="k-receipt-head-number">{transaction.receipt_number}</div>
          </div>
        </div>
        <dl className="k-facts">
          <div><dt>Items on receipt</dt><dd>{transaction.items.length}</dd></div>
          <div><dt>Can be returned here</dt><dd>{returnableCount}</dd></div>
          <div>
            <dt>Return by</dt>
            <dd>{transaction.return_deadline ? parseServerDate(transaction.return_deadline).toLocaleDateString() : "N/A"}</dd>
          </div>
          <div><dt>Total paid</dt><dd>{money(transaction.total_amount)}</dd></div>
        </dl>
      </div>
      <div className="k-note k-note-icon">
        <InfoIcon size={38} />
        <div>
          <h2 className="k-note-title">Item not listed?</h2>
          <p>It may already be returned, or it can't be returned at the kiosk. Tap I need help.</p>
        </div>
      </div>
    </>
  );

  return (
    <KioskLayout title="Choose an item" side={side} onBack={goBack} showCancel>
      <h1 className="k-h1">Which item are you returning?</h1>
      <p className="k-lead k-lead-close">Tap Return this next to the item.</p>
      <ul className="k-items">
        {transaction.items.map((item) => <ItemRow key={item.item_id} item={item} onReturn={handleReturn} />)}
      </ul>
    </KioskLayout>
  );
}

export default ItemSelectionPage;
