import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "../../components/Layout";
import PageWrapper from "../../components/PageWrapper";

function KioskShell() {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <>
      <div className="kiosk-particles" aria-hidden>
        {Array.from({ length: 18 }).map((_, i) => (
          <span key={i} style={{ left: `${5 + Math.random() * 90}%`, bottom: `${Math.random() * 10}%`, width: `${2 + Math.random() * 3}px`, height: `${2 + Math.random() * 3}px`, "--dur": `${8 + Math.random() * 14}s`, "--delay": `${Math.random() * 12}s` }} />
        ))}
      </div>
      <div className="kiosk-topbar">
        <div className="topbar-brand"><span className="topbar-dot" />AutoRefund</div>
        <div className="topbar-time">{time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</div>
        <div className="topbar-status">● SYSTEM ONLINE</div>
      </div>
    </>
  );
}

function ItemSelectionPage() {
  const [transaction, setTransaction] = useState(null);
  const [selectedItem, setSelectedItem] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    const stored = localStorage.getItem("transactionData");
    if (stored) {
      const parsed = JSON.parse(stored);
      const normalizedItems = Array.isArray(parsed.items)
        ? parsed.items.map((item) => ({
            ...item,
            is_refundable: typeof item.is_refundable === "boolean" ? item.is_refundable : true,
            refund_status: item.refund_status || null,
          }))
        : [];
      setTransaction({ ...parsed, items: normalizedItems });
    }
  }, []);

  const handleSelectItem = (item) => {
    if (!item.is_refundable) return;
    setSelectedItem(item);
  };

  const handleNext = () => {
    if (!selectedItem) return;
    localStorage.setItem("selectedItem", JSON.stringify(selectedItem));
    navigate("/customer/verify");
  };

  if (!transaction) {
    return (
      <PageWrapper>
        <KioskShell />
        <Layout title="Item Selection" subtitle="No receipt data found.">
          <div className="isp-no-data">
            <div className="isp-no-data-icon">📋</div>
            <h2>No receipt data found</h2>
            <p>Please scan or enter your receipt first.</p>
            <button className="primary-btn" onClick={() => navigate("/customer/receipt")}>← Scan Receipt</button>
            <button className="ghost-btn" onClick={() => navigate("/")}>← Back to Home</button>
          </div>
        </Layout>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper>
      <KioskShell />
      <Layout title="" subtitle="">
        <div className="kiosk-content">
          {/* Progress */}
          <div className="isp-progress">
            {["Receipt", "Select Item", "Weigh", "Done!"].map((label, i) => (
              <div key={label} className="isp-progress-part">
                <div className={`isp-step ${i === 0 ? "isp-done" : i === 1 ? "isp-active" : ""}`}>
                  <div className="isp-step-circle">{i === 0 ? "✓" : i + 1}</div>
                  <div className="isp-step-label">{label}</div>
                </div>
                {i < 3 && <div className={`isp-progress-line ${i === 0 ? "isp-line-done" : ""}`} />}
              </div>
            ))}
          </div>

          {/* Header */}
          <div className="kiosk-hero" style={{ paddingTop: 32, paddingBottom: 24 }}>
            <div className="kiosk-eyebrow">Step 2 of 3</div>
            <h1 className="page-title">Select Item to Return</h1>
            <p className="page-subtitle">Choose the item from your receipt that you'd like to refund</p>
          </div>

          {/* Guide strip */}
          <div className="kiosk-guide-strip">
            <div className="kgs-item kgs-done"><div className="kgs-icon">📋</div><div className="kgs-label">Receipt scanned</div></div>
            <div className="kgs-item kgs-active"><div className="kgs-icon">📦</div><div className="kgs-label">Select item</div></div>
            <div className="kgs-item"><div className="kgs-icon">⚖️</div><div className="kgs-label">Weigh item</div></div>
            <div className="kgs-item"><div className="kgs-icon">✅</div><div className="kgs-label">Get result</div></div>
          </div>

          {/* Receipt meta */}
          <div className="isp-receipt-bar">
            <div className="isp-rb-item">
              <span className="isp-rb-label">Receipt</span>
              <span className="isp-rb-val isp-mono">{transaction.receipt_number}</span>
            </div>
            <div className="isp-rb-divider" />
            <div className="isp-rb-item">
              <span className="isp-rb-label">Customer</span>
              <span className="isp-rb-val">{transaction.customer_email || "N/A"}</span>
            </div>
            <div className="isp-rb-divider" />
            <div className="isp-rb-item">
              <span className="isp-rb-label">Total Paid</span>
              <span className="isp-rb-val isp-green">${transaction.total_amount}</span>
            </div>
            <div className="isp-rb-divider" />
            <div className="isp-rb-item">
              <span className="isp-rb-label">Items</span>
              <span className="isp-rb-val">{transaction.items.length}</span>
            </div>
          </div>

          <div className="section-label" style={{ marginTop: 20 }}>Select one item to refund</div>

          <div className="items-list">
            {transaction.items.map((item) => {
              const isSelected = selectedItem?.item_id === item.item_id;
              const isDisabled = !item.is_refundable;
              return (
                <label key={item.item_id} className={`item-card ${isSelected ? "selected" : ""} ${isDisabled ? "item-card-disabled" : ""}`}>
                  <input type="radio" name="refundItem" checked={isSelected} disabled={isDisabled} onChange={() => handleSelectItem(item)} />
                  <div className="item-info-block">
                    <h3>{item.name}</h3>
                    <div className="item-tags">
                      <span className="itag">Barcode: {item.barcode}</span>
                      <span className="itag">Qty: {item.quantity}</span>
                      <span className="itag">Expected: {item.expected_weight_grams} g</span>
                    </div>
                    {isDisabled && (
                      <div className="refund-locked-note">
                        {item.refund_status ? `Already submitted for refund (${item.refund_status})` : "Already submitted for refund"}
                      </div>
                    )}
                  </div>
                  {isSelected && !isDisabled && <div className="item-check" aria-hidden>✓</div>}
                </label>
              );
            })}
          </div>

          <div className="btn-row">
            <button className="ghost-btn" onClick={() => navigate("/customer/receipt")}>← Back to Receipt</button>
            <button className="ghost-btn" onClick={() => navigate("/")}>🏠 Home</button>
            <button className="primary-btn" onClick={handleNext} disabled={!selectedItem} style={{ marginLeft: "auto" }}>
              {selectedItem ? `Weigh "${selectedItem.name}" →` : "Select an item to continue"}
            </button>
          </div>
        </div>
      </Layout>

      <style>{`
        @keyframes fsUp{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
        .isp-no-data{display:flex;flex-direction:column;align-items:center;gap:16px;padding:60px 24px;text-align:center}
        .isp-no-data-icon{font-size:56px}
        .isp-no-data h2{font-size:28px;color:#fff;font-family:'Orbitron',sans-serif}
        .isp-no-data p{color:#6882a8;font-size:16px}
        .isp-progress{display:flex;align-items:center;padding:20px 32px;background:rgba(4,10,22,.75);border-radius:18px;border:1px solid rgba(56,189,248,.1);animation:fsUp .4s ease both;gap:0;margin-bottom:8px}
        .isp-progress-part{display:flex;align-items:center;flex:1}
        .isp-step{display:flex;flex-direction:column;align-items:center;gap:7px}
        .isp-step-circle{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;background:rgba(56,189,248,.08);color:#3d5270;border:1px solid rgba(56,189,248,.14)}
        .isp-done .isp-step-circle{background:rgba(16,251,196,.14);color:#10fbc4;border-color:rgba(16,251,196,.3)}
        .isp-active .isp-step-circle{background:linear-gradient(135deg,#0ea5e9,#38bdf8);color:#020810;box-shadow:0 0 20px rgba(56,189,248,.5);border:none}
        .isp-step-label{font-size:11px;color:#3d5270;font-family:'Space Mono',monospace;letter-spacing:.07em;white-space:nowrap}
        .isp-done .isp-step-label{color:#10fbc4}
        .isp-active .isp-step-label{color:#38bdf8}
        .isp-progress-line{flex:1;height:2px;background:rgba(56,189,248,.07);margin:0 6px}
        .isp-line-done{background:linear-gradient(90deg,rgba(16,251,196,.35),rgba(16,251,196,.1))}
        .isp-receipt-bar{display:flex;align-items:center;gap:0;border-radius:16px;background:rgba(4,10,22,.7);border:1px solid rgba(56,189,248,.12);overflow:hidden;margin-bottom:8px;animation:fsUp .45s ease both .28s}
        .isp-rb-item{flex:1;display:flex;flex-direction:column;gap:4px;padding:18px 22px}
        .isp-rb-divider{width:1px;background:rgba(56,189,248,.12);align-self:stretch}
        .isp-rb-label{font-family:'Space Mono',monospace;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:#6882a8}
        .isp-rb-val{font-size:15px;font-weight:600;color:#fff}
        .isp-rb-val.isp-mono{font-family:'Space Mono',monospace;font-size:13px;color:#38bdf8}
        .isp-rb-val.isp-green{color:#22d3a4}
        .item-info-block{flex:1}
        .item-tags{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
        .itag{font-size:12px;font-family:'Space Mono',monospace;color:#6882a8;background:rgba(99,160,255,.07);border:1px solid rgba(99,160,255,.14);border-radius:6px;padding:3px 9px}
        .item-check{width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#0ea5e9,#38bdf8);color:#020810;font-weight:700;font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;align-self:center;box-shadow:0 0 16px rgba(56,189,248,.7)}
        .item-card-disabled{opacity:.62;cursor:not-allowed;border:1px solid rgba(251,191,36,.25)!important;background:rgba(251,191,36,.05)!important}
        .item-card-disabled input{cursor:not-allowed}
        .refund-locked-note{margin-top:12px;display:inline-flex;width:fit-content;padding:6px 10px;border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.03em;color:#fbbf24;background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.22)}
        @media(max-width:600px){.isp-receipt-bar{flex-wrap:wrap}.isp-rb-item{min-width:calc(50% - 1px)}.isp-rb-divider{display:none}}
      `}</style>
    </PageWrapper>
  );
}

export default ItemSelectionPage;