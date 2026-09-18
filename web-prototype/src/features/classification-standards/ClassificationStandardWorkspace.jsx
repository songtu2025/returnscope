import { useEffect, useRef, useState } from "react";
import { ArrowLeft, UploadSimple } from "@phosphor-icons/react";
import Button from "antd/es/button";
import Input from "antd/es/input";
import { Modal } from "../../components/SharedUi";
import { ClassificationExcelImport } from "./ClassificationExcelImport";
import { ClassificationHierarchyChanges } from "./ClassificationHierarchyEditor";
import { ClassificationRuleIssues } from "./ClassificationRuleIssues";
import { ClassificationStandardEditor } from "./ClassificationStandardDraftEditor";
import { ClassificationStandardValidation } from "./ClassificationStandardValidation";
import { ClassificationStructureIssues } from "./ClassificationStructureIssues";
import { ClassificationStandardVersionHistory } from "./ClassificationStandardVersionHistory";
import { contentFromClassificationStandardSnapshot } from "./classificationStandardContent";
import { labelChanges } from "./labelDraftPolicy";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunSummary} ClassificationStandardValidationRunSummary */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("../../shared/api/classificationStandardContracts").ReadableRecognitionProfile} ReadableRecognitionProfile */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {{initiallyEditing: boolean, versions: ClassificationStandardVersion[], notify: (message: string, tone?: string) => void, onDelete: () => void, onRestore: (version: ClassificationStandardVersion) => void, savedContent: ClassificationStandardEditableContent | null, focusLabelCode?: string, isNew: boolean, detail: ClassificationStandardDetail | null, draft: ClassificationStandardDraft | null, content: ClassificationStandardEditableContent, changeReason: string, busy: string, dirty: boolean, validationSources: ClassificationStandardValidationSource[], validationRuns: ClassificationStandardValidationRunSummary[], selectedValidation: ClassificationStandardValidationRunDetail | null, validationSourceId: string, validationSampleSize: ValidationSampleSize, fieldErrors: Partial<ClassificationStandardFieldErrors>, validationAttempt: number, onContentChange: (content: ClassificationStandardEditableContent, field?: string) => void, onReasonChange: (reason: string) => void, onSave: () => void | Promise<void>, onPublish: (validationRunId?: string | null) => void | Promise<void>, onBack: () => void, onValidationSourceChange: (sourceId: string) => void, onValidationSampleSizeChange: (size: ValidationSampleSize) => void, onValidationRun: (file: File | null, comparisonType?: string) => void | Promise<void>, onImport: (event: import("react").ChangeEvent<HTMLInputElement>) => void | Promise<void>, onPrepareExcel: () => Promise<ClassificationStandardDraft>, onApplyExcel: (content: ClassificationStandardEditableContent, filename: string) => void, onValidationSelect: (runId: string) => void | Promise<void>}} ClassificationStandardWorkspaceProps */

/** @param {ClassificationStandardWorkspaceProps} props */
export function ClassificationStandardWorkspace({
  initiallyEditing,
  versions,
  notify,
  onDelete,
  onRestore,
  savedContent,
  focusLabelCode,
  isNew,
  detail,
  draft,
  content,
  changeReason,
  busy,
  dirty,
  validationSources,
  validationRuns,
  selectedValidation,
  validationSourceId,
  validationSampleSize,
  fieldErrors,
  validationAttempt,
  onContentChange,
  onReasonChange,
  onSave,
  onPublish,
  onBack,
  onValidationSourceChange,
  onValidationSampleSizeChange,
  onValidationRun,
  onImport,
  onPrepareExcel,
  onApplyExcel,
  onValidationSelect,
}) {
  const [section, setSection] = useState(isNew ? "settings" : "labels");
  const [confirmBack, setConfirmBack] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [fixRequest, setFixRequest] = useState(
    /** @type {ClassificationStandardValidationIssue | null} */ (null),
  );
  /** @param {ClassificationStandardValidationIssue} issue */
  const fixIssue = (issue) => {
    setSection(
      issue.kind === "invalid_rule" ||
        (!issue.label_code &&
          issue.label_index == null &&
          issue.kind === "missing_field")
        ? "settings"
        : "labels",
    );
    setFixRequest({ ...issue });
  };
  const handledValidationAttempt = useRef(validationAttempt);
  const editable = isNew || detail?.status === "active" || Boolean(draft);
  const baseContent = draft?.base_snapshot
    ? contentFromClassificationStandardSnapshot(draft.base_snapshot)
    : detail?.snapshot
      ? contentFromClassificationStandardSnapshot(detail.snapshot)
      : null;
  const changes = labelChanges(content.labels, baseContent?.labels).filter(
    (entry) => entry.status !== "未修改",
  );
  const contentKeys = /** @type {(keyof ClassificationStandardEditableContent)[]} */ (
    Object.keys(content)
  );
  const settingsChanges = contentKeys.filter(
    (key) =>
      key !== "labels" &&
      JSON.stringify(content[key]) !== JSON.stringify(baseContent?.[key]),
  ).length;
  const changeCount = changes.length + settingsChanges;
  const validationEvidence =
    selectedValidation?.is_current &&
    selectedValidation.status === "completed" &&
    Number(selectedValidation.error_count) === 0 &&
    (selectedValidation.source?.comparison_type ?? "standard_version") ===
      "standard_version"
      ? selectedValidation
      : null;
  const structureBlocked = Boolean(draft?.validation.blocking.length);
  const publishDisabled =
    Boolean(busy) || !draft || dirty || structureBlocked || !changeReason.trim();
  const publishLabel = !draft
    ? "请先保存草稿"
    : dirty
      ? "请先保存修改"
      : structureBlocked
        ? "请先修复结构问题"
        : !changeReason.trim()
          ? "请填写变更说明"
          : "发布并启用";

  useEffect(() => {
    if (!validationAttempt || handledValidationAttempt.current === validationAttempt) {
      return;
    }
    handledValidationAttempt.current = validationAttempt;
    const hasSettingsError =
      fieldErrors.name ||
      fieldErrors.product_context ||
      fieldErrors.variants_empty ||
      fieldErrors.variants?.some((item) => item.category_a || item.category_b);
    setSection(hasSettingsError ? "settings" : "labels");
  }, [fieldErrors, validationAttempt]);

  return (
    <>
      <div className="standard-subpage-heading editor-heading">
        <button
          type="button"
          className="icon-button"
          aria-label="返回"
          onClick={() => (dirty ? setConfirmBack(true) : onBack())}
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>{isNew ? "建立品类与标签体系" : detail?.name}</h1>
          <span>
            {draft
              ? `未发布草稿 r${draft.revision} · 当前启用版本 V${draft.base_version_no}`
              : detail
                ? `${detail.status === "active" ? "当前启用版本" : "已停用版本"} V${detail.version_no}`
                : "新建标准"}
          </span>
        </div>
        {detail && (detail.status === "active" || detail.delete_mode === "delete") && (
          <details className="standard-more-menu">
            <summary>更多</summary>
            <button type="button" disabled={Boolean(busy)} onClick={onDelete}>
              {detail.delete_mode === "delete" ? "删除标准" : "停用标准"}
            </button>
          </details>
        )}
      </div>

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

      <div className="standard-settings-extra" hidden={section !== "settings"}>
        <ClassificationRuleIssues
          content={content}
          onChange={onContentChange}
          focusRequest={fixRequest}
          disabled={!editable || Boolean(busy)}
        />
        <section className="standard-detail-section">
          <h2>识别策略</h2>
          <label>
            当前草稿使用
            <select
              aria-label="识别策略"
              disabled={!editable}
              value={content.recognition_profile ?? "legacy_v3"}
              onChange={(event) =>
                onContentChange({
                  ...content,
                  recognition_profile: /** @type {ReadableRecognitionProfile} */ (
                    event.target.value
                  ),
                })
              }
            >
              <option value="legacy_v3">现有策略 · 定义与关键词</option>
              <option value="semantic_v1">语义策略 · 定义、边界与证据</option>
              <option value="fact_v2">事实策略 · 对象、条件与证据对齐</option>
            </select>
          </label>
          <p>保存只修改草稿；通过发布验证并启用后，新任务才使用该策略。</p>
        </section>
        {!isNew && editable && (
          <section className="standard-json-transfer">
            <div>
              <b>JSON 数据交换</b>
              <span>导入只替换当前草稿的业务内容，不会直接发布。</span>
            </div>
            <label
              className={`secondary-button standard-json-import-button ${
                busy ? "disabled" : ""
              }`}
            >
              <UploadSimple size={15} />
              {busy === "import" ? "导入中" : "导入JSON"}
              <input
                type="file"
                accept="application/json,.json"
                aria-label="选择分类标准 JSON 文件"
                disabled={Boolean(busy)}
                onChange={onImport}
              />
            </label>
          </section>
        )}

        {detail && (
          <ClassificationStandardVersionHistory
            standard={{ ...detail, draft_id: draft?.id }}
            versions={versions}
            onRestore={onRestore}
          />
        )}
      </div>

      <div className="standard-review-panel" hidden={section !== "review"}>
        <section className="standard-editor-section standard-change-preview">
          <header>
            <h2>发布前检查</h2>
            <span>对比当前启用版本</span>
          </header>
          <p>保存草稿不会影响运行中的标准。可以直接发布，也可以先测试验收。</p>
          <ClassificationHierarchyChanges content={content} baseContent={baseContent} />
          {content.recognition_profile !== baseContent?.recognition_profile && (
            <p>
              识别策略：
              {baseContent?.recognition_profile === "fact_v2"
                ? "事实策略"
                : baseContent?.recognition_profile === "semantic_v1"
                  ? "语义策略"
                  : "现有策略"}
              {" → "}
              {content.recognition_profile === "fact_v2"
                ? "事实策略（对象、条件与证据对齐）"
                : content.recognition_profile === "semantic_v1"
                  ? "语义策略（定义、边界与证据）"
                  : "现有策略（定义与关键词）"}
            </p>
          )}
          {changes.length ? (
            changes.map(({ label, before, status }) => (
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
                {
                  /** @type {[string, import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel | null | undefined][]} */ ([
                    ["原", before],
                    ["新", status === "拟停用" ? null : label],
                  ]).map(
                    ([title, value]) =>
                      value &&
                      Boolean(
                        before?.exclusions?.length ||
                        before?.examples?.length ||
                        label.exclusions?.length ||
                        label.examples?.length,
                      ) && (
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
                              {example.sentiment ? ` · ${example.sentiment}` : ""}：
                              {example.text} — {example.explanation}
                            </p>
                          ))}
                        </div>
                      ),
                  )
                }
              </article>
            ))
          ) : (
            <p>标签没有变化。基本信息与分类设置的修改会随草稿一起保存。</p>
          )}
          {JSON.stringify(content.validation_rules) !==
            JSON.stringify(baseContent?.validation_rules ?? {}) && (
            <p className="label-unsaved-hint">
              标签校验规则有变化，请检查相关语义边界、分类指令与 Listing 承诺配置。
            </p>
          )}
          {!dirty && draft && draft.validation.blocking.length > 0 && (
            <ClassificationStructureIssues
              validation={draft.validation}
              content={content}
              onFix={fixIssue}
              busy={Boolean(busy)}
            />
          )}
        </section>
        <section className="standard-change-reason">
          <label>
            变更说明
            <Input
              value={changeReason}
              onChange={(event) => onReasonChange(event.target.value)}
            />
          </label>
          <span>用于版本记录，不影响智能体判断。</span>
        </section>

        <section
          className="standard-required-validation"
          aria-labelledby="standard-required-validation-title"
        >
          <header className="standard-required-validation-heading">
            <div>
              <h2 id="standard-required-validation-title">可选测试验收</h2>
              <p>运行测试可辅助判断分类效果，但不会代替你的发布决定。</p>
            </div>
            <span>可选</span>
          </header>
          {draft ? (
            <ClassificationStandardValidation
              draft={draft}
              sources={validationSources}
              runs={validationRuns}
              selectedRun={selectedValidation}
              sourceId={validationSourceId}
              sampleSize={validationSampleSize}
              busy={busy === "validation"}
              dirty={dirty}
              onSourceChange={onValidationSourceChange}
              onSampleSizeChange={onValidationSampleSizeChange}
              onRun={onValidationRun}
              onSelectRun={onValidationSelect}
            />
          ) : (
            <p>请先保存草稿，再按需运行测试验收。</p>
          )}
        </section>
      </div>
      {editable && (
        <footer className="standard-editor-footer">
          <div role="status">
            <strong>
              {isNew && !draft
                ? dirty
                  ? `有 ${changeCount} 项变更 · 未保存`
                  : "尚未保存"
                : changeCount
                  ? `有 ${changeCount} 项变更${dirty ? " · 未保存" : " · 已保存"}`
                  : "暂无变更"}
            </strong>
            {draft && !dirty && <span>草稿 r{draft.revision}，尚未发布</span>}
          </div>
          <div>
            <Button disabled={Boolean(busy)} onClick={onSave}>
              {busy === "save" ? "保存中" : "保存草稿"}
            </Button>
            {section === "review" ? (
              <button
                type="button"
                className="primary-button"
                disabled={publishDisabled}
                title={publishDisabled ? publishLabel : undefined}
                onClick={() => setConfirmPublish(true)}
              >
                {busy === "publish" ? "启用中" : publishLabel}
              </button>
            ) : (
              <Button
                type="primary"
                disabled={Boolean(busy) || (!dirty && !draft)}
                onClick={() => setSection("review")}
              >
                发布
              </Button>
            )}
          </div>
        </footer>
      )}
      {confirmBack && (
        <Modal
          eyebrow="未保存修改"
          title="离开编辑页？"
          onClose={() => setConfirmBack(false)}
        >
          <div className="label-action-confirm">
            <p>尚未保存的修改会丢失。可以继续编辑并保存草稿，或放弃本次未保存内容。</p>
            <div>
              <Button onClick={() => setConfirmBack(false)}>继续编辑</Button>
              <Button type="primary" danger onClick={onBack}>
                放弃修改并返回
              </Button>
            </div>
          </div>
        </Modal>
      )}
      {confirmPublish && draft && (
        <Modal
          eyebrow="发布标签体系"
          title="发布并立即启用当前草稿？"
          onClose={() => setConfirmPublish(false)}
        >
          <div className="label-action-confirm">
            <p>
              发布后会生成新的不可变版本，并立即用于新任务；当前已发布版本仍保留，可用于恢复。
            </p>
            {validationEvidence ? (
              <p>
                已选择草稿 r{validationEvidence.draft_revision} 的测试记录。
                {validationEvidence.quality_gate?.passed === false
                  ? "自动质量检查未通过，你仍可根据业务判断验收并发布。"
                  : "自动质量检查已通过，仍请以业务判断为准。"}
              </p>
            ) : (
              <p>当前没有可关联的已完成测试，本次将作为直接发布记录。</p>
            )}
            <div>
              <Button onClick={() => setConfirmPublish(false)}>取消</Button>
              {validationEvidence && (
                <Button
                  onClick={() => {
                    setConfirmPublish(false);
                    void onPublish(null);
                  }}
                >
                  直接发布
                </Button>
              )}
              <Button
                type="primary"
                onClick={() => {
                  setConfirmPublish(false);
                  void onPublish(validationEvidence?.id ?? null);
                }}
              >
                {validationEvidence
                  ? validationEvidence.quality_gate?.passed === false
                    ? "接受测试结果并发布"
                    : "验收并发布"
                  : "确认直接发布"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
