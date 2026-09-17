import axios from "axios";

// Backend location. Override in self_refund_frontend/.env.local, e.g.
//   VITE_API_ORIGIN=http://192.168.1.50:5000
// Default: the Flask backend on the same Windows PC.
export const API_ORIGIN = (
  import.meta.env.VITE_API_ORIGIN || "http://127.0.0.1:5000"
).replace(/\/+$/, "");

export const captureUrl = (imagePath) =>
  imagePath ? `${API_ORIGIN}/api/captures/${String(imagePath).split("/").pop()}` : "";

const api = axios.create({
  baseURL: `${API_ORIGIN}/api`,
});

export default api;
