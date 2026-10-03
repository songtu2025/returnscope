import { StandardWorkspaceHeader } from "./StandardWorkspaceHeader";
import { StandardWorkspaceConfirmations } from "./StandardWorkspaceConfirmations";
import { ClassificationExcelImport } from "./ClassificationExcelImport";
import { ClassificationStandardEditor } from "./ClassificationStandardDraftEditor";
import { useStandardWorkspace } from "./useStandardWorkspace";
import { StandardWorkspaceSettings } from "./StandardWorkspaceSettings";
import { StandardWorkspaceReview } from "./StandardWorkspaceReview";
import { StandardWorkspaceFooter } from "./StandardWorkspaceFooter";

/** @param {import("./classificationStandardWorkspaceContracts").ClassificationStandardWorkspaceProps} props */
export function ClassificationStandardWorkspace(props) {
  const state = useStandardWorkspace(props);
  const context = { ...props, ...state };
  const {
    initiallyEditing,
    notify,
    savedContent,
    focusLabelCode,
    content,
    busy,
    fieldErrors,
    validationAttempt,
    onContentChange,
    onPrepareExcel,
    onApplyExcel,
    section,
    setSection,
    fixRequest,
    editable,
    baseContent,
  } = context;
  return (
    <>
      <StandardWorkspaceHeader {...context} />

      <nav className="standard-editor-tabs" aria-label="标准管理分区">
        {[
          ["labels", "标签管理"],
          ["settings", "标准设置"],
        ].map(([value, title]) => (
          <button
            key={value}
            type="button"
            aria-current={section === value ? "page" : undefined}
            onClick={() => setSection(value)}
          >
            {title}
          </button>
        ))}
      </nav>

      <ClassificationStandardEditor
        section={section}
        initiallyEditing={initiallyEditing}
        editable={editable}
        notify={notify}
        busy={Boolean(busy)}
        savedContent={savedContent}
        focusLabelCode={focusLabelCode}
        fixRequest={fixRequest}
        content={content}
        baseContent={baseContent}
        onChange={onContentChange}
        fieldErrors={fieldErrors}
        validationAttempt={validationAttempt}
      />

      {editable && (
        <section className="standard-json-transfer">
          <div>
            <b>Excel 标签框架</b>
            <span>选择工作表与层级列，预览后采用。</span>
          </div>
          <ClassificationExcelImport
            prepareDraft={onPrepareExcel}
            onApply={onApplyExcel}
            disabled={Boolean(busy)}
          />
        </section>
      )}

      <StandardWorkspaceSettings {...context} />

      <StandardWorkspaceReview {...context} />
      {editable && <StandardWorkspaceFooter {...context} />}

      <StandardWorkspaceConfirmations {...context} />
    </>
  );
}
