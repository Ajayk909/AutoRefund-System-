import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import KioskLayout from "../../components/KioskLayout";
import { AlertIcon, BarcodeIcon } from "../../components/Icons";
import agent, { agentErrorMessage } from "../../services/agent";
import useBarcodeScanner from "../../hooks/useBarcodeScanner";

// Bar widths (px) for the barcode drawn on the example receipt.
const BARS = [3, 6, 2, 5, 3, 7, 2, 4, 6, 3, 5, 2, 6, 3, 4, 2, 5, 3, 6, 2];

// Picture of a receipt with the barcode at the bottom, so customers know what to scan.
function ReceiptPicture() {
  return (
    <div className="k-receipt-pic" aria-hidden="true">
      {[150, 236, 200, 236, 120, 180].map((width, i) => <span key={i} className="k-receipt-line" style={{ width }} />)}
      <div className="k-receipt-barcode">
        {BARS.map((width, i) => <span key={i} style={{ width }} />)}
      </div>
      <div className="k-receipt-number">RCP-2001</div>
    </div>
  );
}

function ReceiptScanPage() {
  const [receiptNumber, setReceiptNumber] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scanning, setScanning] = useState(true);
  const navigate = useNavigate();

  const handleContinue = async (manualReceiptNumber) => {
    const value = (manualReceiptNumber ?? receiptNumber).trim();
    if (!value) { setError("Please enter your receipt number first."); return; }
    try {
      setLoading(true); setError("");
      const response = await agent.get(`/transactions/${encodeURIComponent(value)}`);
      localStorage.setItem("transactionData", JSON.stringify(response.data.transaction));
      navigate("/customer/items");
    } catch (err) {
      // 404 = unknown receipt. Other errors (e.g. this kiosk isn't set up)
      // carry a customer-safe message from the server.
      setError(err?.response?.status === 404
        ? "Please check the number and try again."
        : agentErrorMessage(err, "Please check the number and try again."));
    } finally { setLoading(false); }
  };

  // Camera scanner: ask the agent once a second whether it has read a barcode.
  useEffect(() => {
    if (!scanning) return;
    const interval = setInterval(async () => {
      try {
        const res = await agent.get("/receipt/scan");
        if (res.data?.success && res.data?.found && res.data?.barcode) {
          const scannedReceipt = String(res.data.barcode).trim();
          setReceiptNumber(scannedReceipt);
          setScanning(false);
          await handleContinue(scannedReceipt);
        }
      } catch { /* scanner not ready yet: keep asking */ }
    }, 1000);
    return () => clearInterval(interval);
  }, [scanning]);

  // USB barcode scanner (HID keyboard mode) - works even without input focus
  useBarcodeScanner((code) => {
    if (loading) return;
    setReceiptNumber(code);
    setError("");
    handleContinue(code);
  });

  const side = (
    <>
      <div className="k-card k-card-roomy k-find">
        <h2 className="k-card-title">Where to find it</h2>
        <ReceiptPicture />
        <p className="k-find-caption">The barcode is at the bottom of your receipt.</p>
      </div>
      <div className="k-note">
        <p>No receipt? A store employee can help at the customer service desk.</p>
      </div>
    </>
  );

  return (
    <KioskLayout title="Scan your receipt" side={side} onBack={() => navigate("/")} showCancel>
      <h1 className="k-h1">Scan your receipt</h1>
      <p className="k-lead">Hold the barcode under the scanner or in front of the camera.</p>

      <div className="k-scan">
        <span className="k-scan-icon"><BarcodeIcon size={74} stroke={2} /></span>
        <div className="k-scan-text">
          <div className="k-scan-title">
            {loading ? "Looking up your receipt…" : scanning ? "Ready to scan" : "Scanning paused"}
          </div>
          <div className="k-scan-sub">
            {loading ? receiptNumber : scanning ? "Waiting for a barcode…" : "You can type the receipt number below."}
          </div>
        </div>
        <button className="k-btn k-btn-small" type="button" onClick={() => setScanning((prev) => !prev)}>
          {scanning ? "Pause scanning" : "Resume scanning"}
        </button>
      </div>

      <label className="k-label" htmlFor="receipt-number">Or type the receipt number</label>
      <div className="k-input-row">
        <input
          id="receipt-number"
          className={`k-input ${error ? "k-input-error" : ""}`}
          type="text" placeholder="e.g. RCP-2001"
          value={receiptNumber}
          onChange={(e) => { setReceiptNumber(e.target.value); setError(""); }}
          onKeyDown={(e) => e.key === "Enter" && handleContinue()}
          autoFocus
        />
        <button className="k-btn k-btn-primary k-find-btn" onClick={() => handleContinue()} disabled={loading}>
          {loading ? "Looking up your receipt…" : "Find my receipt"}
        </button>
      </div>

      {error && (
        <div className="k-error" role="alert">
          <AlertIcon size={40} stroke={2} />
          <div>
            <div className="k-error-title">
              {receiptNumber.trim() ? "We couldn't find that receipt" : "Enter your receipt number"}
            </div>
            <div>{error}</div>
          </div>
        </div>
      )}
    </KioskLayout>
  );
}

export default ReceiptScanPage;
