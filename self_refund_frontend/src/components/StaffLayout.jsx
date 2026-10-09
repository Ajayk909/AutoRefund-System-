import { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { ArrowLeftIcon, GridIcon, InboxIcon, ListIcon, LogoIcon } from "./Icons";
import useStageScale from "../hooks/useStageScale";
import api from "../services/api";
import { clearStaffSession, getStaffUser } from "../services/staffSession";
import "../staff.css";

function TopBar({ staff, onSignOut }) {
  return (
    <header className="s-top">
      <span className="s-logo"><LogoIcon size={20} stroke={2.25} /></span>
      <span className="s-brand">AutoRefund</span>
      <span className="s-brand-sub">Staff</span>
      {staff && (
        <>
          <span className="s-signed-in">Signed in as {staff.full_name}</span>
          <button className="s-signout" onClick={onSignOut}>Sign out</button>
        </>
      )}
    </header>
  );
}

// The frame of every staff screen: blue top bar and the left navigation.
// `bare` (sign-in page) shows only the top bar.
// Pages that already load the review queue pass `pendingCount`, so the badge
// stays right after approve/reject; otherwise the layout loads it itself.
export default function StaffLayout({ bare = false, pendingCount, children }) {
  const navigate = useNavigate();
  const scale = useStageScale(1440, 900);
  const staff = bare ? null : getStaffUser();
  const [loadedCount, setLoadedCount] = useState(null);

  useEffect(() => {
    if (bare || pendingCount !== undefined) return;
    api.get("/refunds/pending")
      .then((r) => setLoadedCount((r.data.refunds || []).length))
      .catch(() => { /* badge just stays hidden */ });
  }, [bare, pendingCount]);

  const signOut = async () => {
    try { await api.post("/staff/logout"); } catch { /* session may already be gone */ }
    clearStaffSession();
    navigate("/employee/login");
  };

  const count = pendingCount ?? loadedCount;
  const navClass = ({ isActive }) => `s-nav-item ${isActive ? "s-nav-active" : ""}`;

  return (
    <div className="stage-wrap">
      <div className={`stage s-screen ${bare ? "s-screen-bare" : ""}`} style={{ transform: `scale(${scale})` }}>
        <TopBar staff={staff} onSignOut={signOut} />
        {!bare && (
          <nav className="s-nav">
            <NavLink to="/employee/dashboard" className={navClass}><GridIcon size={20} stroke={1.5} /> Overview</NavLink>
            <NavLink to="/employee/pending" className={navClass}>
              <InboxIcon size={20} stroke={1.5} /> Review queue
              {count !== null && <span className="s-badge">{count}</span>}
            </NavLink>
            <NavLink to="/employee/logs" className={navClass}><ListIcon size={20} stroke={1.5} /> Return log</NavLink>
            <NavLink to="/" className="s-nav-kiosk"><ArrowLeftIcon size={18} stroke={1.5} /> Kiosk start screen</NavLink>
          </nav>
        )}
        <main className="s-main">{children}</main>
      </div>
    </div>
  );
}
