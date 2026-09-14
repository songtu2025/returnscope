import { taxonomyPath } from "../../lib/taxonomyPresentation";

const SENTIMENTS = { NEGATIVE: "负向", POSITIVE: "正向", NEUTRAL: "中性" };

export function ClassificationLabelDefinition({
  hierarchical,
  editable,
  editing,
  published,
  removed,
  busy,
  label,
  entry,
  content,
  baseContent,
  allowedGroups,
  fieldErrors,
  errorId,
  labelFieldRefs,
  updateLabel,
  onChange,
  onRequestReplacement,
}) {
  return (
    <>
      {hierarchical && editable && editing && (
        <label>
          上级分类
          <select
            ref={(node) =>
              labelFieldRefs.current.set(`${entry.index}.parent_code`, node)
            }
            aria-label="标签的上级分类"
            value={label.parent_code || ""}
            onChange={(event) => {
              const next = { ...label, parent_code: event.target.value };
              updateLabel({
                parent_code: next.parent_code,
                group: taxonomyPath(content, next)[0] || "",
              });
            }}
          >
            <option value="" disabled>
              请选择上级分类
            </option>
            {(content.categories ?? []).map((item) => (
              <option key={item.code} value={item.code}>
                {taxonomyPath(content, item).join(" → ")}
              </option>
            ))}
          </select>
        </label>
      )}
      {hierarchical && published && editable && editing && (
        <label>
          标签名称
          <input
            aria-label="已发布标签名称"
            value={label.name}
            onChange={(event) => updateLabel({ name: event.target.value })}
          />
        </label>
      )}
      {published || !editing ? (
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
            <dl>
              <div>
                <dt>{hierarchical ? "标签路径" : "标签分组"}</dt>
                <dd>
                  {taxonomyPath(removed ? baseContent : content, label).join(" → ")}
                </dd>
              </div>
              <div>
                <dt>评价方向</dt>
                <dd>
                  {label.allowed_sentiments
                    .map((value) => SENTIMENTS[value])
                    .join(" / ")}
                </dd>
              </div>
            </dl>
            <h3>判定说明（可选）</h3>
            <p>{label.description || "依据标签名称和完整路径理解"}</p>
          </section>
        </>
      ) : (
        <section className="standard-editor-fields label-new-fields">
          <label>
            标签名称
            <input
              ref={(node) => {
                labelFieldRefs.current.set(`${entry.index}.name`, node);
              }}
              aria-label={`标签名称 ${entry.index + 1}`}
              aria-invalid={Boolean(fieldErrors.labels?.[entry.index]?.name)}
              aria-describedby={
                fieldErrors.labels?.[entry.index]?.name
                  ? `${errorId}-label-${entry.index}-name`
                  : undefined
              }
              value={label.name}
              onChange={(event) => updateLabel({ name: event.target.value })}
            />
            {fieldErrors.labels?.[entry.index]?.name && (
              <span
                className="standard-field-error"
                id={`${errorId}-label-${entry.index}-name`}
              >
                {fieldErrors.labels[entry.index].name}
              </span>
            )}
          </label>
          {!hierarchical && (
            <label>
              标签分组
              <select
                ref={(node) => {
                  labelFieldRefs.current.set(`${entry.index}.group`, node);
                }}
                aria-label={`标签分组 ${entry.index + 1}`}
                aria-invalid={Boolean(fieldErrors.labels?.[entry.index]?.group)}
                aria-describedby={
                  fieldErrors.labels?.[entry.index]?.group
                    ? `${errorId}-label-${entry.index}-group`
                    : undefined
                }
                value={label.group}
                onChange={(event) => updateLabel({ group: event.target.value })}
              >
                {!allowedGroups.includes(label.group) && (
                  <option value={label.group}>{label.group || "请选择分组"}</option>
                )}
                {allowedGroups.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              {fieldErrors.labels?.[entry.index]?.group && (
                <span
                  className="standard-field-error"
                  id={`${errorId}-label-${entry.index}-group`}
                >
                  {fieldErrors.labels[entry.index].group}
                </span>
              )}
            </label>
          )}
          <label className="wide-field">
            标签编码
            <input
              ref={(node) => {
                labelFieldRefs.current.set(`${entry.index}.code`, node);
              }}
              aria-label={`标签编码 ${entry.index + 1}`}
              aria-invalid={Boolean(fieldErrors.labels?.[entry.index]?.code)}
              aria-describedby={
                fieldErrors.labels?.[entry.index]?.code
                  ? `${errorId}-label-${entry.index}-code`
                  : undefined
              }
              value={label.code}
              onChange={(event) =>
                updateLabel({ code: event.target.value.toUpperCase() })
              }
            />
            {fieldErrors.labels?.[entry.index]?.code && (
              <span
                className="standard-field-error"
                id={`${errorId}-label-${entry.index}-code`}
              >
                {fieldErrors.labels[entry.index].code}
              </span>
            )}
          </label>
          <label className="wide-field">
            判定说明（可选）
            <textarea
              ref={(node) => {
                labelFieldRefs.current.set(`${entry.index}.description`, node);
              }}
              rows={5}
              aria-label={`判定说明（可选） ${entry.index + 1}`}
              value={label.description ?? ""}
              placeholder="有特殊边界时补充，无需重复标签名称"
              onChange={(event) => updateLabel({ description: event.target.value })}
            />
          </label>
          <fieldset className="wide-field label-sentiment-options">
            <legend>支持的评价方向</legend>
            {Object.entries(SENTIMENTS).map(([value, name]) => (
              <label key={value}>
                <input
                  ref={(node) => {
                    if (value === "NEGATIVE")
                      labelFieldRefs.current.set(
                        `${entry.index}.allowed_sentiments`,
                        node,
                      );
                  }}
                  type="checkbox"
                  checked={label.allowed_sentiments.includes(value)}
                  onChange={(event) =>
                    updateLabel({
                      allowed_sentiments: event.target.checked
                        ? [...label.allowed_sentiments, value]
                        : label.allowed_sentiments.filter((item) => item !== value),
                    })
                  }
                />
                {name}
              </label>
            ))}
          </fieldset>
          <fieldset className="wide-field label-sentiment-options">
            <legend>统计与复核</legend>
            {[
              ["required_review_labels", "使用此标签时必须人工复核"],
              ...(label.allowed_sentiments.includes("NEUTRAL")
                ? [["neutral_reason_labels", "中性反馈可作为退货原因"]]
                : []),
            ].map(([field, title]) => (
              <label key={field}>
                <input
                  type="checkbox"
                  checked={(content.validation_rules?.[field] ?? []).includes(
                    label.code,
                  )}
                  onChange={(event) => {
                    const values = content.validation_rules?.[field] ?? [];
                    onChange({
                      ...content,
                      validation_rules: {
                        ...content.validation_rules,
                        [field]: event.target.checked
                          ? [...new Set([...values, label.code])]
                          : values.filter((code) => code !== label.code),
                      },
                    });
                  }}
                />
                {title}
              </label>
            ))}
          </fieldset>
        </section>
      )}
    </>
  );
}
