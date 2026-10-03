/** @param {{index: number, isExpanded: boolean, setExpanded: import("react").Dispatch<import("react").SetStateAction<number | null>>}} props */
export function MysqlPreviewToggle({ index, isExpanded, setExpanded }) {
  return (
    <button
      type="button"
      className="mysql-preview-detail-button"
      aria-label={`${isExpanded ? "收起" : "查看"}第${index + 1}条详情`}
      aria-expanded={isExpanded}
      aria-controls={isExpanded ? `mysql-preview-detail-${index}` : undefined}
      onClick={() => setExpanded(isExpanded ? null : index)}
    >
      {isExpanded ? "收起" : "详情"}
    </button>
  );
}
