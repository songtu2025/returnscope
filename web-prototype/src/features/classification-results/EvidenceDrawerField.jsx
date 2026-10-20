/** @param {{label: string, value?: unknown, title?: string}} props */
export function EvidenceDrawerField({ label, value, title }) {
  return (
    <div className="drawer-field">
      <span>{label}</span>
      <b title={title}>{value ? String(value) : "未提供"}</b>
    </div>
  );
}
