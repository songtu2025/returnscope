import { LabelDefinitionFields, LabelParentSelector } from "./LabelDefinitionFields";
import { LabelPublishedDefinition } from "./LabelPublishedDefinition";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {{hierarchical: boolean, editable: boolean, editing: boolean, published: boolean, busy: boolean, label: ClassificationStandardEditableLabel, entry: {index: number}, content: ClassificationStandardEditableContent, allowedGroups: string[], fieldErrors: Partial<ClassificationStandardFieldErrors>, errorId: string, labelFieldRefs: import("react").RefObject<Map<string, HTMLElement | null>>, updateLabel: (updates: Partial<ClassificationStandardEditableLabel>) => void, onChange: (content: ClassificationStandardEditableContent) => void, onRequestReplacement: () => void}} ClassificationLabelDefinitionProps */

/** @param {ClassificationLabelDefinitionProps} props */
export function ClassificationLabelDefinition({
  hierarchical,
  editable,
  editing,
  published,
  busy,
  label,
  entry,
  content,
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
        <LabelParentSelector
          label={label}
          entry={entry}
          content={content}
          labelFieldRefs={labelFieldRefs}
          updateLabel={updateLabel}
        />
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
        <LabelPublishedDefinition
          hierarchical={hierarchical}
          editable={editable}
          editing={editing}
          published={published}
          busy={busy}
          content={content}
          label={label}
          onRequestReplacement={onRequestReplacement}
        />
      ) : (
        <LabelDefinitionFields
          hierarchical={hierarchical}
          label={label}
          entry={entry}
          content={content}
          allowedGroups={allowedGroups}
          fieldErrors={fieldErrors}
          errorId={errorId}
          labelFieldRefs={labelFieldRefs}
          updateLabel={updateLabel}
          onChange={onChange}
        />
      )}
    </>
  );
}
