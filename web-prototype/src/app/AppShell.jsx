/** @typedef {{sidebar: import("react").ReactNode, topbar: import("react").ReactNode, warning: import("react").ReactNode, children: import("react").ReactNode, overlays: import("react").ReactNode}} AppShellProps */

/** @param {AppShellProps} props */
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
