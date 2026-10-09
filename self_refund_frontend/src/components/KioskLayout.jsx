import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Dialog from "./Dialog";
import { ArrowLeftIcon, CloseIcon, HelpIcon, LogoIcon, ScaleIcon } from "./Icons";
import useStageScale from "../hooks/useStageScale";
import { resetAndGoHome } from "../services/kioskSession";
import "../kiosk.css";

// The frame of every customer screen: blue top bar, white main panel with a
// summary column on the right, and the bottom toolbar.
// Each page decides which toolbar buttons show:
//   onBack     -> shows Back (left)
//   showCancel -> shows Cancel return
//   scaleText  -> shows the live scale weight (weigh page only)
// "I need help" is always there.
export default function KioskLayout({ title, side, panelClass = "", onBack, showCancel = false, scaleText, children }) {
  const navigate = useNavigate();
  const [openDialog, setOpenDialog] = useState(""); // "", "help" or "cancel"
  const scale = useStageScale(1920, 1080);

  return (
    <div className="stage-wrap">
      <div className="stage k-screen" style={{ transform: `scale(${scale})` }}>
        <header className="k-top">
          <span className="k-logo"><LogoIcon size={26} stroke={2.5} /></span>
          <span className="k-brand">AutoRefund</span>
          <span className="k-divider" />
          <span className="k-title">{title}</span>
          <span className="k-kiosk-name">Self-service returns · Kiosk 1</span>
        </header>

        <main className="k-body">
          <section className={`k-panel ${panelClass}`}>{children}</section>
          <aside className="k-side">{side}</aside>
        </main>

        <footer className="k-toolbar">
          {onBack && (
            <button className="k-tool" onClick={onBack}>
              <ArrowLeftIcon size={28} /> Back
            </button>
          )}
          <div className="k-toolbar-right">
            <button className="k-tool k-tool-help" onClick={() => setOpenDialog("help")}>
              <HelpIcon size={28} /> I need help
            </button>
            {showCancel && (
              <button className="k-tool k-tool-cancel" onClick={() => setOpenDialog("cancel")}>
                <CloseIcon size={28} /> Cancel return
              </button>
            )}
            {scaleText && (
              <div className="k-scale">
                <ScaleIcon size={28} /> Scale <strong>{scaleText}</strong>
              </div>
            )}
          </div>
        </footer>

        {openDialog === "help" && (
          <Dialog
            title="Need help?"
            actions={<button className="k-btn k-btn-primary" onClick={() => setOpenDialog("")}>OK</button>}
          >
            <p className="dialog-text">
              Please go to the customer service desk. An employee can finish this return with you.
            </p>
          </Dialog>
        )}

        {openDialog === "cancel" && (
          <Dialog
            title="Cancel this return?"
            actions={
              <>
                <button className="k-btn k-btn-secondary" onClick={() => setOpenDialog("")}>Keep going</button>
                <button className="k-btn k-btn-danger" onClick={() => resetAndGoHome(navigate)}>Cancel return</button>
              </>
            }
          >
            <p className="dialog-text">
              Nothing has been refunded. You'll go back to the start screen.
            </p>
          </Dialog>
        )}
      </div>
    </div>
  );
}
