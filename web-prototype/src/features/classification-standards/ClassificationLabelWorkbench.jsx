import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";
import { useEffect, useId, useRef, useState } from "react";
import { ArrowCounterClockwise, Copy, Plus, X } from "@phosphor-icons/react";
import { EmptyState, Modal } from "../../components/SharedUi";
import { labelChanges, reconcileLabelRules, sameLabel } from "./labelDraftPolicy";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { ClassificationLabelBoundaries } from "./ClassificationLabelBoundaries";
import { ClassificationLabelDefinition } from "./ClassificationLabelDefinition";
import { ClassificationLabelDirectory } from "./ClassificationLabelDirectory";

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
  const [selected, setSelected] = useState(() =>
    Math.max(
      0,
      content.labels.findIndex((label) => label.code === focusLabelCode),
    ),
  );
  const [editing, setEditing] = useState(initiallyEditing);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("");
  const [pending, setPending] = useState(null);
  const [keywordText, setKeywordText] = useState("");
  const [origins, setOrigins] = useState({});
  const selectedRef = useRef(null);
  const addLabelRef = useRef(null);
  const emptyLabelRef = useRef(null);
  const labelFieldRefs = useRef(new Map());
  const pendingFocusRef = useRef(null);
  const handledFixRef = useRef(null);
  const focusedAttemptRef = useRef(0);
  const errorId = useId();
  useEffect(() => {
    const target = selectedRef.current;
    if (target)
      target.parentElement.scrollTop =
        target.offsetTop -
        target.parentElement.clientHeight / 2 +
        target.offsetHeight / 2;
  }, [selected, query, group]);
  const entries = labelChanges(content.labels, baseContent?.labels);
  const entry =
    typeof selected === "number"
      ? entries.find((item) => item.index === selected)
      : entries.find((item) => item.index < 0 && item.label.code === selected);
  const label = entry?.label;
  const published = Boolean(entry?.before) && !(label?.code in origins);
  const removed = entry?.status === "拟停用";
  const saved =
    savedContent?.labels.find((item) => item.code === label?.code) ??
    savedContent?.labels.find((item) => item.code === origins[label?.code]);
  const labelDirty = label && (removed ? Boolean(saved) : !sameLabel(label, saved));
  const groups = [...new Set(entries.map((item) => item.label.group).filter(Boolean))];
  const hierarchical = content.structure_version === 2;
  const allowedGroups = hierarchical
    ? (content.categories ?? [])
        .filter((item) => !item.parent_code)
        .map((item) => item.name)
    : content.validation_rules?.allowed_groups?.length
      ? content.validation_rules.allowed_groups
      : BUSINESS_GROUPS;
  const matches = entries.filter(
    ({ label: item }) =>
      (!group || item.group === group) &&
      [
        item.name,
        item.code,
        item.description,
        ...taxonomyPath(content, item),
        ...(item.keywords ?? []),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );

  const conflictCodes = new Set(
    (content.validation_rules?.conflicting_label_sets ?? [])
      .filter((codes) => codes.includes(label?.code))
      .flat(),
  );
  const relatedLabels = content.labels.filter(
    (item) => item.code !== label?.code && conflictCodes.has(item.code),
  );

  const updateLabel = (updates) => {
    const field = Object.keys(updates)[0];
    if (updates.code !== undefined && updates.code !== label.code) {
      setOrigins((current) => {
        const next = { ...current, [updates.code]: current[label.code] ?? label.code };
        delete next[label.code];
        return next;
      });
    }
    onChange(
      {
        ...content,
        labels: content.labels.map((item, index) =>
          index === entry.index ? { ...item, ...updates } : item,
        ),
      },
      `labels.${entry.index}.${field}`,
    );
  };
  const changeLabels = (labels, restoredCode, field) =>
    onChange(
      {
        ...content,
        labels,
        validation_rules: hierarchical
          ? content.validation_rules
          : reconcileLabelRules(
              content.validation_rules,
              labels,
              baseContent?.validation_rules,
              restoredCode,
            ),
      },
      field,
    );
  const selectLabel = (value) => {
    setSelected(value);
    setKeywordText("");
  };
  const addLabel = (source) => {
    setEditing(true);
    const usedCodes = new Set(entries.map((item) => item.label.code));
    const prefix = source
      ? `${source.code}_V`
      : hierarchical
        ? `LABEL_${crypto.randomUUID().replaceAll("-", "").toUpperCase()}_`
        : "NEW_LABEL_";
    let suffix = source ? 2 : 1;
    while (usedCodes.has(`${prefix}${suffix}`)) suffix += 1;
    const newLabel = source
      ? { ...source, code: `${prefix}${suffix}`, allowed_claim_ids: [] }
      : {
          code: `${prefix}${suffix}`,
          name: "",
          group: allowedGroups.includes(group) ? group : allowedGroups[0] || "",
          ...(hierarchical
            ? { parent_code: content.categories?.[0]?.code ?? null }
            : {}),
          description: "",
          keywords: [],
          allowed_sentiments: ["NEGATIVE"],
          allowed_claim_ids: [],
        };
    const labels = source
      ? content.labels.map((item, index) => (index === entry.index ? newLabel : item))
      : [...content.labels, newLabel];
    setOrigins((current) => ({ ...current, [newLabel.code]: source?.code ?? null }));
    changeLabels(labels, undefined, "labels_empty");
    selectLabel(source ? entry.index : labels.length - 1);
    setQuery("");
    setGroup("");
    setPending(null);
  };
  const commitKeywords = (text) => {
    const values = text
      .split(/[,，;；\n]+/)
      .map((word) => word.trim())
      .filter(Boolean);
    if (values.length)
      updateLabel({ keywords: [...new Set([...(label.keywords ?? []), ...values])] });
    setKeywordText("");
  };
  const retireLabel = () => {
    const labels = content.labels.filter((_item, index) => index !== entry.index);
    changeLabels(labels);
    selectLabel(published ? label.code : Math.max(0, entry.index - 1));
    setPending(null);
  };
  const undoLabel = () => {
    setOrigins((current) => {
      const next = { ...current };
      delete next[label.code];
      if (saved) delete next[saved.code];
      return next;
    });
    if (removed && saved) {
      changeLabels([...content.labels, saved], saved.code);
      selectLabel(content.labels.length);
    } else if (saved)
      changeLabels(
        content.labels.map((item, index) => (index === entry.index ? saved : item)),
        saved.code,
      );
    else {
      changeLabels(content.labels.filter((_item, index) => index !== entry.index));
      selectLabel(0);
    }
    setKeywordText("");
  };

  useEffect(() => {
    if (
      !validationAttempt ||
      busy ||
      section !== "labels" ||
      focusedAttemptRef.current === validationAttempt
    ) {
      return;
    }
    if (fieldErrors.labels_empty) {
      const target = emptyLabelRef.current || addLabelRef.current;
      if (target) {
        focusedAttemptRef.current = validationAttempt;
        target.focus();
      }
      return;
    }
    const index = fieldErrors.labels?.findIndex(
      (item) => item.name || item.group || item.code,
    );
    if (index < 0) return;
    const errors = fieldErrors.labels[index];
    const field = ["name", "group", "code"].find((key) => errors[key]);
    pendingFocusRef.current = { attempt: validationAttempt, index, field };
    setSelected(index);
    setEditing(true);
  }, [busy, fieldErrors, section, validationAttempt]);

  useEffect(() => {
    if (!fixRequest || section !== "labels" || handledFixRef.current === fixRequest)
      return;
    const index = fixRequest.label_code
      ? content.labels.findIndex((item) => item.code === fixRequest.label_code)
      : fixRequest.label_index;
    if (index < 0 || !content.labels[index]) return;
    handledFixRef.current = fixRequest;
    pendingFocusRef.current = { index, field: fixRequest.field || "description" };
    setQuery("");
    setGroup("");
    setSelected(index);
    setEditing(true);
  }, [content.labels, fixRequest, section]);

  useEffect(() => {
    const pendingFocus = pendingFocusRef.current;
    if (
      !pendingFocus ||
      busy ||
      !editing ||
      section !== "labels" ||
      selected !== pendingFocus.index
    ) {
      return;
    }
    const target = labelFieldRefs.current.get(
      `${pendingFocus.index}.${pendingFocus.field}`,
    );
    if (!target) return;
    target.focus();
    focusedAttemptRef.current = pendingFocus.attempt;
    pendingFocusRef.current = null;
  }, [busy, editing, section, selected, fixRequest]);

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
        busy={busy}
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
        {label ? (
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
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => setEditing((value) => !value)}
                  >
                    {editing ? "完成编辑" : "编辑"}
                  </button>
                )}
                {editable && labelDirty && (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={undoLabel}
                  >
                    <ArrowCounterClockwise size={15} />
                    撤销当前修改
                  </button>
                )}
                {editable && !removed && (
                  <details className="standard-more-menu">
                    <summary>更多</summary>
                    <button
                      type="button"
                      disabled={busy || content.labels.length <= 1}
                      onClick={(event) => {
                        event.currentTarget.closest("details").open = false;
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
                  {editable && (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        changeLabels([...content.labels, label], label.code);
                        selectLabel(content.labels.length);
                      }}
                    >
                      恢复到草稿
                    </button>
                  )}
                </div>
              ) : (
                <>
                  <ClassificationLabelDefinition
                    hierarchical={hierarchical}
                    editable={editable}
                    editing={editing}
                    published={published}
                    removed={removed}
                    busy={busy}
                    label={label}
                    entry={entry}
                    content={content}
                    baseContent={baseContent}
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
                    onFieldRef={(field, node) =>
                      labelFieldRefs.current.set(`${entry.index}.${field}`, node)
                    }
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
              <button
                type="button"
                className="secondary-button"
                onClick={() => setPending(null)}
              >
                继续编辑
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  pending.type === "replace" ? addLabel(label) : retireLabel()
                }
              >
                {pending.type === "replace" ? "创建替代标签" : "确认移除"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
