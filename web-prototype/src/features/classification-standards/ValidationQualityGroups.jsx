import { ISSUE_LABELS } from "./classificationValidationQualityGroups";
import { ValidationFactTrace } from "./ValidationFactTrace";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationItem} ClassificationStandardValidationItem */
/** @typedef {import("./classificationValidationQualityGroups").QualityGroup} QualityGroup */
/** @param {{item: ClassificationStandardValidationItem, group: QualityGroup}} props */
function QualityGroupItem({ item, group }) {
  return (
    <details>
      <summary>
        来源第 {item.source_row ?? "—"} 行 · {item.comment.slice(0, 70)}
      </summary>
      <p>{item.comment}</p>
      <ul>
        {Object.entries(ISSUE_LABELS)
          .filter(([key]) => (item.reference_comparison?.draft?.[key] ?? 0) > 0)
          .map(([key, label]) => (
            <li key={key}>
              {label}：{item.reference_comparison?.draft?.[key] ?? 0}
            </li>
          ))}
        {item.draft.review_reasons?.map((reason, index) => (
          <li key={`review-${index}`}>{reason}</li>
        ))}
      </ul>
      {(item.draft.unknown_semantics?.length ?? 0) > 0 && (
        <p>
          {group.informational ? "留空事实：" : "未覆盖语义："}
          {(item.draft.unknown_semantics ?? [])
            .map((unit) =>
              typeof unit === "string"
                ? unit
                : unit.opinion || unit.evidence || unit.reason || "请查看逐条结果",
            )
            .join("；")}
        </p>
      )}
      <ValidationFactTrace result={item.draft} />
    </details>
  );
}
/** @param {{group: QualityGroup}} props */
function QualityGroupDetails({ group }) {
  return (
    <details className="standard-quality-group">
      <summary>
        {group.title} · {group.items.length} 条{group.informational ? "记录" : "待检查"}
      </summary>
      <p>{group.note}</p>
      {group.items.length === 0 ? (
        <p>当前没有对应信号；不代表该类问题已全部排除。</p>
      ) : (
        group.items.map((item) => (
          <QualityGroupItem key={item.classification_key} item={item} group={group} />
        ))
      )}
    </details>
  );
}
/** @param {{groups: QualityGroup[]}} props */
export function ValidationQualityGroups({ groups }) {
  return groups.map((group) => <QualityGroupDetails key={group.title} group={group} />);
}
