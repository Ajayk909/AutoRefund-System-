function Layout({ title, subtitle, children }) {
  return (
    <div className="app-shell">
      <div className="page-card">
        {title && <h1 className="page-title">{title}</h1>}
        {subtitle && <p className="page-subtitle">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}

export default Layout;