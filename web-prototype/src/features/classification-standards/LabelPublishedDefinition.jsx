import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { CLASSIFICATION_LABEL_SENTIMENTS as SENTIMENTS } from "./classificationLabelSentiments";
/** @typedef {import("./ClassificationLabelDefinition").ClassificationLabelDefinitionProps} DefinitionProps */
/** @param {Pick<DefinitionProps, "hierarchical" | "content" | "label">} props */
function LabelDefinitionMetadata({ hierarchical, content, label }) {
  return (
    <dl>
      <div>
        <dt>{hierarchical ? "标签路径" : "标签分组"}</dt>
        <dd>{taxonomyPath(content, label).join(" → ")}</dd>
      </div>
      <div>
        <dt>评价方向</dt>
        <dd>
          {label.allowed_sentiments.map((value) => SENTIMENTS[value]).join(" / ")}
        </dd>
      </div>
    </dl>
  );
}
/** @param {Pick<DefinitionProps, "hierarchical" | "editable" | "editing" | "published" | "busy" | "content" | "label" | "onRequestReplacement">} props */
export function LabelPublishedDefinition({
  hierarchical,
  editable,
  editing,
  published,
  busy,
  content,
  label,
  onRequestReplacement,
}) {
  return (
    <>
      {editable && editing && published && (
        <div className="label-published-note">
          <span>已发布标签语义保持稳定，可直接补充关键词。</span>
          <button type="button" disabled={busy} onClick={onRequestReplacement}>
            修改说明：创建替代标签 →
          </button>
        </div>
      )}
      <section className="label-business-definition">
        <LabelDefinitionMetadata
          hierarchical={hierarchical}
          content={content}
          label={label}
        />
        <h3>判定说明（可选）</h3>
        <p>{label.description || "依据标签名称和完整路径理解"}</p>
      </section>
    </>
  );
}
