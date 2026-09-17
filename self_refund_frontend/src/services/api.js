import axios from "axios";
import { clearStaffSession, getStaffToken } from "./staffSession";

// Backend location. Override in self_refund_frontend/.env.local, e.g.
//   VITE_API_ORIGIN=http://192.168.1.50:5000
// Default: the Flask backend on the same Windows PC.
export const API_ORIGIN = (
  import.meta.env.VITE_API_ORIGIN || "http://127.0.0.1:5000"
).replace(/\/+$/, "");

const api = axios.create({
  baseURL: `${API_ORIGIN}/api`,
});

api.interceptors.request.use((config) => {
  const token = getStaffToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const res = error?.response;
    const onEmployeePage = window.location.pathname.startsWith("/employee")
      && window.location.pathname !== "/employee/login";
    if (res?.status === 401 && res?.data?.code === "AUTH_REQUIRED" && onEmployeePage) {
      clearStaffSession();
      window.location.assign("/employee/login");
    }
    return Promise.reject(error);
  }
);

// Friendly text for an API error (never raw technical details).
export function errorMessage(err, fallback = "Something went wrong. Please try again.") {
  return err?.response?.data?.message || fallback;
}

export default api;
