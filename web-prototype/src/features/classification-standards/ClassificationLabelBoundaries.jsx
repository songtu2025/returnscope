import { LabelBoundaryExamples } from "./LabelBoundaryExamples";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {{label: ClassificationStandardEditableLabel, editing: boolean, onChange: (updates: Partial<ClassificationStandardEditableLabel>) => void, onFieldRef: (field: string, node: HTMLElement | null) => void}} ClassificationLabelBoundariesProps */

/** @param {ClassificationLabelBoundariesProps} props */
function LabelExclusions({ label, editing, onChange, onFieldRef }) {
  const exclusions = label.exclusions ?? [];
  return (
    <div>
      <h3>排除说明</h3>
      {editing ? (
        <textarea
          aria-label="排除说明"
          ref={(node) => onFieldRef("exclusions", node)}
          rows={3}
          placeholder="每行说明一种不适用情况；避免重复判定说明"
          value={exclusions.join("\n")}
          onChange={(event) => onChange({ exclusions: event.target.value.split("\n") })}
        />
      ) : (
        <ul>
          {exclusions.map((text, index) => (
            <li key={index}>{text}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
/** @param {ClassificationLabelBoundariesProps} props */
export function ClassificationLabelBoundaries({
  label,
  editing,
  onChange,
  onFieldRef,
}) {
  const exclusions = label.exclusions ?? [];
  const examples = label.examples ?? [];
  if (!editing && !exclusions.length && !examples.length) return null;
  return (
    <section className="label-boundaries">
      {(editing || exclusions.length > 0) && (
        <LabelExclusions
          label={label}
          editing={editing}
          onChange={onChange}
          onFieldRef={onFieldRef}
        />
      )}
      {(editing || examples.length > 0) && (
        <LabelBoundaryExamples
          label={label}
          editing={editing}
          onChange={onChange}
          onFieldRef={onFieldRef}
        />
      )}
    </section>
  );
}
