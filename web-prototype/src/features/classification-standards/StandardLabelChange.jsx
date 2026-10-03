/** @typedef {import("./classificationStandardWorkspaceContracts").StandardWorkspaceContext} StandardWorkspaceContext */
/** @typedef {Pick<StandardWorkspaceContext["changes"][number], "label" | "before" | "status">} LabelChange */

/** @param {LabelChange} entry */
export function StandardLabelChange({ label, before, status }) {
  return (
    <article key={label.code}>
      <header>
        <strong>{label.name || "未命名标签"}</strong>
        <span className="label-change-badge changed">{status}</span>
      </header>
      <code>{label.code}</code>
      <p>{label.description || "依据标签名称和完整路径理解"}</p>
      {status === "已修改" && (
        <div>
          <span>原搜索别名：{before?.keywords?.join("、") || "无"}</span>
          <span>新搜索别名：{label.keywords?.join("、") || "无"}</span>
        </div>
      )}
      <StandardLabelBoundaries label={label} before={before} status={status} />{" "}
    </article>
  );
}
/** @param {LabelChange} entry */
function StandardLabelBoundaries({ label, before, status }) {
  return (
    <>
      {" "}
      {
        /** @type {[string, import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel | null | undefined][]} */ ([
          ["原", before],
          ["新", status === "拟停用" ? null : label],
        ]).map(
          ([title, value]) =>
            value &&
            hasBoundaryChanges(before, label) && (
              <div key={title}>
                <span>
                  {title}排除说明：{value.exclusions?.join("；") || "无"}
                </span>
                <span>
                  {title}判定示例：{value.examples?.length ? "" : "无"}
                </span>
                {value.examples?.map((example, index) => (
                  <p key={index}>
                    {example.applies ? "适用" : "不适用"}
                    {example.sentiment ? ` · ${example.sentiment}` : ""}：{example.text}{" "}
                    — {example.explanation}
                  </p>
                ))}
              </div>
            ),
        )
      }
    </>
  );
}
/** @param {LabelChange["before"]} before @param {LabelChange["label"]} label */
function hasBoundaryChanges(before, label) {
  return Boolean(
    before?.exclusions?.length ||
    before?.examples?.length ||
    label.exclusions?.length ||
    label.examples?.length,
  );
}
