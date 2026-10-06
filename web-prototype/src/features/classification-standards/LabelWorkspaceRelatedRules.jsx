/** @typedef {import("./ClassificationLabelWorkbench").ClassificationLabelWorkbenchProps} WorkbenchProps */
/** @typedef {ReturnType<typeof import("./useClassificationLabelWorkbenchController").useClassificationLabelWorkbenchController>} Controller */
/** @param {Pick<Controller,"relatedLabels"|"setQuery"|"setGroup"|"selectLabel"> & Pick<WorkbenchProps,"content"> & {label: NonNullable<Controller["label"]>}} props */
export function LabelWorkspaceRelatedRules({
  relatedLabels,
  setQuery,
  setGroup,
  selectLabel,
  content,
  label,
}) {
  return (
    <>
      {relatedLabels.length > 0 && (
        <section className="label-related-rules">
          <h3>同时出现时需复核</h3>
          <p>这些标签同时出现时，需检查各自的证据与适用范围。</p>
          {relatedLabels.map((item) => (
            <button
              type="button"
              key={item.code}
              className="secondary-button"
              onClick={() => {
                setQuery("");
                setGroup("");
                selectLabel(content.labels.indexOf(item));
              }}
            >
              {item.name}
            </button>
          ))}
        </section>
      )}
      {label.allowed_claim_ids?.length > 0 && (
        <details className="label-related-rules">
          <summary>关联承诺（{label.allowed_claim_ids.length}）</summary>
          <p>实际适用范围以具体 Listing 的承诺配置为准。</p>
          {label.allowed_claim_ids.map((id) => (
            <code key={id}>{id} </code>
          ))}
        </details>
      )}
    </>
  );
}
