import { useId } from "react";
import { LabelWorkspaceHeader } from "./LabelWorkspaceHeader";
import { LabelKeywordEditor } from "./LabelKeywordEditor";
import { LabelWorkspaceRelatedRules } from "./LabelWorkspaceRelatedRules";
import { LabelActionConfirmation } from "./LabelActionConfirmation";
import { Plus } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { EmptyState } from "../../components/SharedUi";
import { ClassificationLabelBoundaries } from "./ClassificationLabelBoundaries";
import { ClassificationLabelDefinition } from "./ClassificationLabelDefinition";
import { ClassificationLabelDirectory } from "./ClassificationLabelDirectory";
import { useClassificationLabelWorkbenchController } from "./useClassificationLabelWorkbenchController";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */

/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, savedContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, busy: boolean, editable: boolean, initiallyEditing: boolean, notify: (message: string, tone?: string) => void, fieldErrors?: Partial<ClassificationStandardFieldErrors>, validationAttempt?: number, section: string}} ClassificationLabelWorkbenchProps */

/** @param {ClassificationLabelWorkbenchProps} props */
export function ClassificationLabelWorkbench({
  content,
  baseContent,
  savedContent,
  onChange,
  focusLabelCode,
  fixRequest,
  busy,
  editable,
  initiallyEditing,
  notify,
  fieldErrors = {},
  validationAttempt = 0,
  section,
}) {
  const errorId = useId();
  const {
    selected,
    editing,
    query,
    group,
    pending,
    keywordText,
    selectedRef,
    addLabelRef,
    emptyLabelRef,
    labelFieldRefs,
    entry,
    label,
    published,
    removed,
    labelDirty,
    groups,
    hierarchical,
    allowedGroups,
    matches,
    relatedLabels,
    setEditing,
    setQuery,
    setGroup,
    setPending,
    setKeywordText,
    updateLabel,
    selectLabel,
    addLabel,
    commitKeywords,
    retireLabel,
    restoreLabel,
    undoLabel,
  } = useClassificationLabelWorkbenchController({
    content,
    baseContent,
    savedContent,
    onChange,
    focusLabelCode,
    fixRequest,
    busy,
    initiallyEditing,
    fieldErrors,
    validationAttempt,
    section,
  });

  return (
    <div className="label-workbench">
      <ClassificationLabelDirectory
        content={content}
        baseContent={baseContent}
        matches={matches}
        groups={groups}
        query={query}
        group={group}
        selected={selected}
        hierarchical={hierarchical}
        editable={editable}
        busy={Boolean(busy)}
        selectedRef={selectedRef}
        addLabelRef={addLabelRef}
        onAdd={() => addLabel()}
        onSelect={selectLabel}
        onQueryChange={setQuery}
        onGroupChange={setGroup}
        onResetFilters={() => {
          setQuery("");
          setGroup("");
        }}
      />
      <div className="label-workspace" aria-label="当前标签编辑区">
        {fieldErrors.labels_empty && (
          <p className="standard-field-error" id={`${errorId}-labels-empty`}>
            {fieldErrors.labels_empty}
          </p>
        )}
        {label && entry ? (
          <>
            <LabelWorkspaceHeader
              label={label}
              notify={notify}
              editable={editable}
              removed={removed}
              editing={editing}
              setEditing={setEditing}
              labelDirty={labelDirty}
              busy={busy}
              undoLabel={undoLabel}
              content={content}
              published={published}
              setPending={setPending}
            />
            <div className="label-workspace-scroll" key={`${selected}-${removed}`}>
              {removed ? (
                <div className="label-workspace-notice">
                  <h3>此标签拟在下一版本停用</h3>
                  <p>当前线上标准与历史结果不受影响，发布草稿后才生效。</p>
                  {editable && <Button onClick={restoreLabel}>恢复到草稿</Button>}
                </div>
              ) : (
                <>
                  <ClassificationLabelDefinition
                    hierarchical={hierarchical}
                    editable={editable}
                    editing={editing}
                    published={published}
                    busy={Boolean(busy)}
                    label={label}
                    entry={entry}
                    content={content}
                    allowedGroups={allowedGroups}
                    fieldErrors={fieldErrors}
                    errorId={errorId}
                    labelFieldRefs={labelFieldRefs}
                    updateLabel={updateLabel}
                    onChange={onChange}
                    onRequestReplacement={() => setPending({ type: "replace" })}
                  />
                  <ClassificationLabelBoundaries
                    label={label}
                    editing={editable && editing}
                    onChange={updateLabel}
                    onFieldRef={(field, node) => {
                      labelFieldRefs.current.set(`${entry.index}.${field}`, node);
                    }}
                  />
                  <LabelKeywordEditor
                    label={label}
                    editable={editable}
                    editing={editing}
                    updateLabel={updateLabel}
                    entry={entry}
                    keywordText={keywordText}
                    setKeywordText={setKeywordText}
                    commitKeywords={commitKeywords}
                    content={content}
                  />
                  <LabelWorkspaceRelatedRules
                    relatedLabels={relatedLabels}
                    setQuery={setQuery}
                    setGroup={setGroup}
                    selectLabel={selectLabel}
                    content={content}
                    label={label}
                  />
                </>
              )}
            </div>
          </>
        ) : (
          <EmptyState
            icon={Plus}
            title="开始建立标签体系"
            description="新增标签后，在右侧填写名称，并按需补充判定说明和关键词。"
            action={
              editable && (
                <button
                  ref={emptyLabelRef}
                  type="button"
                  className="primary-button"
                  aria-describedby={
                    fieldErrors.labels_empty ? `${errorId}-labels-empty` : undefined
                  }
                  onClick={() => addLabel()}
                >
                  创建第一个标签
                </button>
              )
            }
          />
        )}
      </div>
      {pending && (
        <LabelActionConfirmation
          pending={pending}
          published={published}
          setPending={setPending}
          label={label}
          addLabel={addLabel}
          retireLabel={retireLabel}
        />
      )}
    </div>
  );
}
