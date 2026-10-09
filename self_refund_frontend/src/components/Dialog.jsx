// A simple pop-up box: dims the screen, shows a title, any content and the
// action buttons. Used by the kiosk (help, cancel) and the staff screens.
export default function Dialog({ title, children, actions, className = "" }) {
  return (
    <div className="dialog-backdrop">
      <div className={`dialog ${className}`} role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <h2 id="dialog-title" className="dialog-title">{title}</h2>
        {children}
        <div className="dialog-actions">{actions}</div>
      </div>
    </div>
  );
}
