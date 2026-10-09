import agent from "./agent";

// Ends the customer's return: forgets the saved receipt, item and result,
// tells the kiosk agent the session is over, and goes back to the start screen.
export function resetAndGoHome(navigate) {
  localStorage.removeItem("transactionData");
  localStorage.removeItem("selectedItem");
  localStorage.removeItem("refundResult");
  agent.post("/session/end").catch(() => { /* the session also expires by itself */ });
  navigate("/");
}
