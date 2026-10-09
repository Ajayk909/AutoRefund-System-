import { useNavigate } from "react-router-dom";
import KioskLayout from "../components/KioskLayout";
import { CardIcon, CheckIcon, LockIcon, ReceiptIcon, ScaleIcon } from "../components/Icons";

const STEPS = [
  { icon: <ReceiptIcon size={40} />, title: "Scan your receipt", text: "Use the barcode at the bottom." },
  { icon: <ScaleIcon size={40} />, title: "Place the item on the scale", text: "The kiosk takes a photo too." },
  { icon: <CardIcon size={40} />, title: "Get your refund", text: "Back to your original payment." },
];

const BRING = ["Your receipt, paper or on your phone", "The item, with all its parts", "The box, if you still have it"];

function HomePage() {
  const navigate = useNavigate();

  const side = (
    <>
      <div className="k-card k-card-roomy">
        <h2 className="k-card-title">Before you start</h2>
        <ul className="k-checklist">
          {BRING.map((text) => (
            <li key={text}>
              <span className="k-check"><CheckIcon size={24} /></span>
              {text}
            </li>
          ))}
        </ul>
      </div>

      <div className="k-note k-note-roomy">
        <h2 className="k-note-title">Need a hand?</h2>
        <p>Tap I need help at the bottom of the screen at any time. A store employee can finish the return with you.</p>
      </div>

      <button className="k-staff-btn" onClick={() => navigate("/employee/login")}>
        <LockIcon size={24} /> Staff sign in
      </button>
    </>
  );

  return (
    <KioskLayout title="Welcome" side={side} panelClass="k-panel-roomy">
      <h1 className="k-h1">Return an item</h1>
      <p className="k-lead">Scan your receipt, put the item on the scale, and the kiosk checks it for you.</p>

      <ol className="k-steps">
        {STEPS.map((step, i) => (
          <li key={step.title} className="k-step">
            <span className="k-step-icon">{step.icon}</span>
            <span className="k-step-label">Step {i + 1}</span>
            <span className="k-step-title">{step.title}</span>
            <span className="k-step-text">{step.text}</span>
          </li>
        ))}
      </ol>

      <button className="k-btn k-btn-primary k-btn-big k-start-btn" onClick={() => navigate("/customer/receipt")}>
        Start return
      </button>
    </KioskLayout>
  );
}

export default HomePage;
