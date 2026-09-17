import { useId } from "react";
import { ArrowCounterClockwise, Copy, Plus, X } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { EmptyState, Modal } from "../../components/SharedUi";
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
            <header>
              <div>
                <h2>{label.name || "新建标签"}</h2>
                <div className="label-code-line">
                  <code>{label.code}</code>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="复制标签编码"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(label.code);
                        notify("标签编码已复制");
                      } catch {
                        notify("复制失败，请选中编码手动复制", "error");
                      }
                    }}
                  >
                    <Copy size={14} />
                  </button>
                </div>
              </div>
              <div className="label-workspace-actions">
                {editable && !removed && (
                  <Button onClick={() => setEditing((value) => !value)}>
                    {editing ? "完成编辑" : "编辑"}
                  </Button>
                )}
                {editable && labelDirty && (
                  <Button
                    disabled={Boolean(busy)}
                    icon={<ArrowCounterClockwise size={15} />}
                    onClick={undoLabel}
                  >
                    撤销当前修改
                  </Button>
                )}
                {editable && !removed && (
                  <details className="standard-more-menu">
                    <summary>更多</summary>
                    <button
                      type="button"
                      disabled={Boolean(busy) || content.labels.length <= 1}
                      onClick={(event) => {
                        const menu = event.currentTarget.closest("details");
                        if (menu) menu.open = false;
                        setPending({ type: "retire" });
                      }}
                    >
                      {published ? "停用标签" : "移除新标签"}
                    </button>
                  </details>
                )}
              </div>
            </header>
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
                  <details className="label-keyword-editor">
                    <summary>搜索别名（可选） · {label.keywords?.length ?? 0}</summary>
                    <p>
                      {["semantic_v1", "fact_v2"].includes(content.recognition_profile)
                        ? "仅用于管理页面搜索，不参与当前语义策略分类。"
                        : "当前仍使用旧策略：这些词同时用于搜索和模型提示。切换语义策略并发布后，仅用于搜索。"}
                    </p>
                    <h3>
                      搜索别名 <span>{label.keywords?.length ?? 0}</span>
                    </h3>

                    <div className="label-keyword-tokens">
                      {label.keywords?.map((word, index) => (
                        <span key={index}>
                          {word}
                          {editable && editing && (
                            <button
                              type="button"
                              aria-label={`移除搜索别名 ${word}`}
                              onClick={() =>
                                updateLabel({
                                  keywords: label.keywords.filter(
                                    (_word, i) => i !== index,
                                  ),
                                })
                              }
                            >
                              <X size={13} />
                            </button>
                          )}
                        </span>
                      ))}
                    </div>
                    {editable && editing && (
                      <input
                        aria-label={`搜索别名 ${entry.index + 1}`}
                        value={keywordText}
                        placeholder="添加搜索别名，回车确认；支持逗号分隔"
                        onChange={(event) => setKeywordText(event.target.value)}
                        onBlur={() => commitKeywords(keywordText)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                            event.preventDefault();
                            commitKeywords(keywordText);
                          }
                        }}
                      />
                    )}
                    {!label.keywords?.length && !editing && <p>未配置搜索别名。</p>}
                  </details>
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
        <Modal
          eyebrow="标签草稿"
          title={
            pending.type === "replace"
              ? "创建替代标签"
              : published
                ? "停用此标签？"
                : "移除新标签？"
          }
          onClose={() => setPending(null)}
        >
          <div className="label-action-confirm">
            <p>
              {pending.type === "replace"
                ? "将复制名称、判定说明和关键词，生成新编码，并将旧标签标记为拟停用。新标签不继承旧标签的承诺关联与专用校验规则；发布前请在标准设置中核对相关指令。"
                : "仅修改当前草稿。相关标签校验引用会同步清理，已发布标准和历史结果保持原样。"}
            </p>
            <div>
              <Button onClick={() => setPending(null)}>继续编辑</Button>
              <Button
                type="primary"
                onClick={() =>
                  pending.type === "replace" ? addLabel(label) : retireLabel()
                }
              >
                {pending.type === "replace" ? "创建替代标签" : "确认移除"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
