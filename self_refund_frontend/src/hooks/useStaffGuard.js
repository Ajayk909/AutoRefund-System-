import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getStaffToken, getStaffUser } from "../services/staffSession";

// Sends the user to the login page when no staff session exists.
// UX only: the backend enforces authorization on every staff request.
export default function useStaffGuard() {
  const navigate = useNavigate();
  const token = getStaffToken();
  useEffect(() => {
    if (!token) navigate("/employee/login", { replace: true });
  }, [token, navigate]);
  return getStaffUser() || {};
}
