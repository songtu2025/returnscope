export function AppShell({ sidebar, topbar, warning, children, overlays }) {
  return (
    <div className="app-shell">
      {sidebar}
      <div className="workspace">
        {topbar}
        {warning}
        <main className="page-canvas">{children}</main>
      </div>
      {overlays}
    </div>
  );
}
