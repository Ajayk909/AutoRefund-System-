import axios from "axios";

// The Windows kiosk agent on this PC. Customer screens talk ONLY to the agent:
// it owns the camera, scale and scanner and forwards to the Core API with the
// kiosk's credential. No credentials or hardware values come from the browser.
// Override in self_refund_frontend/.env.local:  VITE_AGENT_ORIGIN=http://127.0.0.1:5100
export const AGENT_ORIGIN = (
  import.meta.env.VITE_AGENT_ORIGIN || "http://127.0.0.1:5100"
).replace(/\/+$/, "");

const agent = axios.create({
  baseURL: `${AGENT_ORIGIN}/api`,
  timeout: 30000,
});

// Friendly text for an agent error. If the agent itself can't be reached, say
// so plainly - never imply that a return went through.
export function agentErrorMessage(err, fallback = "Something went wrong. Please try again.") {
  if (!err?.response) {
    return "The kiosk isn't ready right now. Nothing has been refunded. Please ask an employee for help.";
  }
  return err.response.data?.message || fallback;
}

export default agent;
