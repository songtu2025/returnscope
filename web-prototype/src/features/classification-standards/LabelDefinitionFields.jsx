import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { LabelDefinitionPolicy } from "./LabelDefinitionPolicy";
/** @typedef {import("./ClassificationLabelDefinition").ClassificationLabelDefinitionProps} DefinitionProps */
/** @typedef {Pick<DefinitionProps, "label" | "entry" | "content" | "allowedGroups" | "fieldErrors" | "errorId" | "labelFieldRefs" | "updateLabel" | "onChange">} FieldsProps */

/** @param {Pick<DefinitionProps, "label" | "entry" | "content" | "labelFieldRefs" | "updateLabel">} props */
export function LabelParentSelector({
  label,
  entry,
  content,
  labelFieldRefs,
  updateLabel,
}) {
  return (
    <label>
      上级分类
      <select
        ref={(node) => {
          labelFieldRefs.current.set(`${entry.index}.parent_code`, node);
        }}
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
  );
}

/** @param {{field: "name" | "code", props: FieldsProps}} options */
function LabelIdentityField({ field, props }) {
  const { label, entry, fieldErrors, errorId, labelFieldRefs, updateLabel } = props;
  const title = field === "name" ? "标签名称" : "标签编码";
  const error = fieldErrors.labels?.[entry.index]?.[field];
  return (
    <label className={field === "code" ? "wide-field" : undefined}>
      {title}
      <input
        ref={(node) => {
          labelFieldRefs.current.set(`${entry.index}.${field}`, node);
        }}
        aria-label={`${title} ${entry.index + 1}`}
        aria-invalid={Boolean(error)}
        aria-describedby={
          error ? `${errorId}-label-${entry.index}-${field}` : undefined
        }
        value={label[field]}
        onChange={(event) =>
          updateLabel({
            [field]:
              field === "code" ? event.target.value.toUpperCase() : event.target.value,
          })
        }
      />
      {error && (
        <span
          className="standard-field-error"
          id={`${errorId}-label-${entry.index}-${field}`}
        >
          {error}
        </span>
      )}
    </label>
  );
}

/** @param {FieldsProps} props */
function LabelGroupField({
  label,
  entry,
  allowedGroups,
  fieldErrors,
  errorId,
  labelFieldRefs,
  updateLabel,
}) {
  const error = fieldErrors.labels?.[entry.index]?.group;
  return (
    <label>
      标签分组
      <select
        ref={(node) => {
          labelFieldRefs.current.set(`${entry.index}.group`, node);
        }}
        aria-label={`标签分组 ${entry.index + 1}`}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${errorId}-label-${entry.index}-group` : undefined}
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
      {error && (
        <span
          className="standard-field-error"
          id={`${errorId}-label-${entry.index}-group`}
        >
          {error}
        </span>
      )}
    </label>
  );
}

/** @param {Pick<FieldsProps, "label" | "entry" | "labelFieldRefs" | "updateLabel">} props */
function LabelDescriptionField({ label, entry, labelFieldRefs, updateLabel }) {
  return (
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
  );
}

/** @param {FieldsProps & {hierarchical: boolean}} props */
export function LabelDefinitionFields({ hierarchical, ...props }) {
  return (
    <section className="standard-editor-fields label-new-fields">
      <LabelIdentityField field="name" props={props} />
      {!hierarchical && <LabelGroupField {...props} />}
      <LabelIdentityField field="code" props={props} />
      <LabelDescriptionField {...props} />
      <LabelDefinitionPolicy
        label={props.label}
        entry={props.entry}
        labelFieldRefs={props.labelFieldRefs}
        updateLabel={props.updateLabel}
        content={props.content}
        onChange={props.onChange}
      />
    </section>
  );
}
