import { useState } from "react";
import { useNavigate } from "react-router-dom";
import StaffLayout from "../../components/StaffLayout";
import { AlertIcon, ArrowLeftIcon, LockIcon } from "../../components/Icons";
import api from "../../services/api";
import { saveStaffSession } from "../../services/staffSession";

function EmployeeLoginPage() {
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleLogin = async () => {
    if (!employeeId.trim() || !password.trim()) { setError("Please enter both Employee ID and password."); return; }
    try {
      setLoading(true); setError("");
      const res = await api.post("/staff/login", { username: employeeId, password });
      saveStaffSession(res.data.token, res.data.staff);
      navigate("/employee/dashboard");
    } catch (err) {
      setError(err?.response?.status === 429
        ? err.response.data.message
        : "Invalid credentials. Please try again.");
    }
    finally { setLoading(false); }
  };

  const onEnter = (e) => e.key === "Enter" && handleLogin();

  return (
    <StaffLayout bare>
      <div className="s-login">
        <div className="s-card s-login-card">
          <span className="s-icon-tile"><LockIcon size={24} stroke={2} /></span>
          <h1 className="s-login-title">Staff sign in</h1>
          <p className="s-muted">Use your employee ID and password.</p>

          <label className="s-label" htmlFor="employee-id">Employee ID</label>
          <input id="employee-id" className="s-input" type="text" value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)} onKeyDown={onEnter} autoFocus />

          <label className="s-label" htmlFor="password">Password</label>
          <input id="password" className={`s-input ${error ? "s-input-error" : ""}`} type="password" value={password}
            onChange={(e) => setPassword(e.target.value)} onKeyDown={onEnter} />

          {error && (
            <div className="s-error" role="alert"><AlertIcon size={20} stroke={1.5} /> {error}</div>
          )}

          <button className="s-btn s-btn-primary s-login-btn" onClick={handleLogin} disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </div>
        <button className="s-link" onClick={() => navigate("/")}>
          <ArrowLeftIcon size={16} stroke={2} /> Back to kiosk start screen
        </button>
      </div>
    </StaffLayout>
  );
}

export default EmployeeLoginPage;
