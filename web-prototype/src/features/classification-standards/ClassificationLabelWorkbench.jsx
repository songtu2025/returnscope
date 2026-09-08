import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";
import { useEffect, useRef, useState } from "react";
import {
  ArrowCounterClockwise,
  Copy,
  MagnifyingGlass,
  Plus,
  X,
} from "@phosphor-icons/react";
import { EmptyState, Modal } from "../../components/SharedUi";
import { labelChanges, reconcileLabelRules, sameLabel } from "./labelDraftPolicy";

const SENTIMENTS = { NEGATIVE: "负向", POSITIVE: "正向", NEUTRAL: "中性" };

export function ClassificationLabelWorkbench({
  content,
  baseContent,
  savedContent,
  onChange,
  focusLabelCode,
  busy,
  editable,
  initiallyEditing,
  notify,
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
  const allowedGroups = content.validation_rules?.allowed_groups?.length
    ? content.validation_rules.allowed_groups
    : BUSINESS_GROUPS;
  const matches = entries.filter(
    ({ label: item }) =>
      (!group || item.group === group) &&
      [item.name, item.code, item.description, ...(item.keywords ?? [])]
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
    if (updates.code !== undefined && updates.code !== label.code) {
      setOrigins((current) => {
        const next = { ...current, [updates.code]: current[label.code] ?? label.code };
        delete next[label.code];
        return next;
      });
    }
    onChange({
      ...content,
      labels: content.labels.map((item, index) =>
        index === entry.index ? { ...item, ...updates } : item,
      ),
    });
  };
  const changeLabels = (labels, restoredCode) =>
    onChange({
      ...content,
      labels,
      validation_rules: reconcileLabelRules(
        content.validation_rules,
        labels,
        baseContent?.validation_rules,
        restoredCode,
      ),
    });
  const selectLabel = (value) => {
    setSelected(value);
    setKeywordText("");
  };
  const addLabel = (source) => {
    setEditing(true);
    const usedCodes = new Set(entries.map((item) => item.label.code));
    const prefix = source ? `${source.code}_V` : "NEW_LABEL_";
    let suffix = source ? 2 : 1;
    while (usedCodes.has(`${prefix}${suffix}`)) suffix += 1;
    const newLabel = source
      ? { ...source, code: `${prefix}${suffix}`, allowed_claim_ids: [] }
      : {
          code: `${prefix}${suffix}`,
          name: "",
          group: allowedGroups.includes(group) ? group : allowedGroups[0] || "",
          description: "",
          keywords: [],
          allowed_sentiments: ["NEGATIVE"],
          allowed_claim_ids: [],
        };
    const labels = source
      ? content.labels.map((item, index) => (index === entry.index ? newLabel : item))
      : [...content.labels, newLabel];
    setOrigins((current) => ({ ...current, [newLabel.code]: source?.code ?? null }));
    changeLabels(labels);
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

  return (
    <div className="label-workbench">
      <aside className="label-directory" aria-label="标签目录">
        <header>
          <strong>
            标签目录 <span>{content.labels.length}</span>
          </strong>
          {editable && (
            <button
              type="button"
              className="icon-button"
              aria-label="增加标签"
              disabled={busy}
              onClick={() => addLabel()}
            >
              <Plus size={17} />
            </button>
          )}
        </header>
        <label className="standard-search-box">
          <MagnifyingGlass size={16} />
          <input
            type="search"
            aria-label="搜索标签"
            placeholder="搜索标签或别名"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <select
          aria-label="筛选标签分组"
          value={group}
          onChange={(event) => setGroup(event.target.value)}
        >
          <option value="">全部分组</option>
          {groups.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
        <div className="label-directory-scroll">
          {matches.map((item) => {
            const value = item.index < 0 ? item.label.code : item.index;
            return (
              <button
                ref={selected === value ? selectedRef : undefined}
                key={item.index < 0 ? `removed-${item.label.code}` : item.index}
                type="button"
                aria-current={selected === value ? "true" : undefined}
                disabled={busy}
                onClick={() => selectLabel(value)}
              >
                <span>
                  <b>{item.label.name || "未命名标签"}</b>
                  <small>{item.label.group || "未分组"}</small>
                </span>
                {item.status !== "未修改" && (
                  <span
                    className={`label-change-badge ${item.status === "拟停用" ? "removed" : "changed"}`}
                  >
                    {item.status}
                  </span>
                )}
              </button>
            );
          })}
          {!matches.length && (
            <p className="label-directory-empty">
              没有匹配的标签。
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setGroup("");
                }}
              >
                重置筛选
              </button>
            </p>
          )}
        </div>
      </aside>
      <div className="label-workspace" aria-label="当前标签编辑区">
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
                  {published || !editing ? (
                    <>
                      {editable && editing && published && (
                        <div className="label-published-note">
                          <span>已发布定义保持稳定，可直接补充关键词。</span>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => setPending({ type: "replace" })}
                          >
                            修改定义：创建替代标签 →
                          </button>
                        </div>
                      )}
                      <section className="label-business-definition">
                        <h3>业务定义</h3>
                        <p>{label.description}</p>
                        <dl>
                          <div>
                            <dt>标签分组</dt>
                            <dd>{label.group}</dd>
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
                      </section>
                    </>
                  ) : (
                    <section className="standard-editor-fields label-new-fields">
                      <label>
                        标签名称
                        <input
                          aria-label={`标签名称 ${entry.index + 1}`}
                          value={label.name}
                          onChange={(event) =>
                            updateLabel({ name: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        标签分组
                        <select
                          aria-label={`标签分组 ${entry.index + 1}`}
                          value={label.group}
                          onChange={(event) =>
                            updateLabel({ group: event.target.value })
                          }
                        >
                          {!allowedGroups.includes(label.group) && (
                            <option value={label.group}>
                              {label.group || "请选择分组"}
                            </option>
                          )}
                          {allowedGroups.map((name) => (
                            <option key={name} value={name}>
                              {name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="wide-field">
                        标签编码
                        <input
                          aria-label={`标签编码 ${entry.index + 1}`}
                          value={label.code}
                          onChange={(event) =>
                            updateLabel({ code: event.target.value.toUpperCase() })
                          }
                        />
                      </label>
                      <label className="wide-field">
                        业务定义
                        <textarea
                          rows={5}
                          aria-label={`业务定义 ${entry.index + 1}`}
                          value={label.description}
                          onChange={(event) =>
                            updateLabel({ description: event.target.value })
                          }
                        />
                      </label>
                      <fieldset className="wide-field label-sentiment-options">
                        <legend>支持的评价方向</legend>
                        {Object.entries(SENTIMENTS).map(([value, name]) => (
                          <label key={value}>
                            <input
                              type="checkbox"
                              checked={label.allowed_sentiments.includes(value)}
                              onChange={(event) =>
                                updateLabel({
                                  allowed_sentiments: event.target.checked
                                    ? [...label.allowed_sentiments, value]
                                    : label.allowed_sentiments.filter(
                                        (item) => item !== value,
                                      ),
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
                              checked={(
                                content.validation_rules?.[field] ?? []
                              ).includes(label.code)}
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
                  <LabelBoundaries
                    label={label}
                    editing={editable && editing}
                    onChange={updateLabel}
                  />
                  <details className="label-keyword-editor">
                    <summary>搜索别名（可选） · {label.keywords?.length ?? 0}</summary>
                    <p>
                      {content.recognition_profile === "semantic_v1"
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
            description="新增标签后，在右侧填写定义和关键词。"
            action={
              editable && (
                <button
                  type="button"
                  className="primary-button"
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
                ? "将复制名称、定义和关键词，生成新编码，并将旧标签标记为拟停用。新标签不继承旧标签的承诺关联与专用校验规则；发布前请在标准设置中核对相关指令。"
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

function LabelBoundaries({ label, editing, onChange }) {
  const exclusions = label.exclusions ?? [];
  const examples = label.examples ?? [];
  const updateExample = (index, change) =>
    onChange({
      examples: examples.map((item, position) =>
        position === index ? { ...item, ...change } : item,
      ),
    });
  if (!editing && !exclusions.length && !examples.length) return null;
  return (
    <section className="label-boundaries">
      {(editing || exclusions.length > 0) && (
        <div>
          <h3>排除说明</h3>
          {editing ? (
            <textarea
              aria-label="排除说明"
              rows={3}
              placeholder="每行说明一种不适用情况；避免重复业务定义"
              value={exclusions.join("\n")}
              onChange={(event) =>
                onChange({ exclusions: event.target.value.split("\n") })
              }
            />
          ) : (
            <ul>
              {exclusions.map((text, index) => (
                <li key={index}>{text}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {(editing || examples.length > 0) && (
        <div>
          <h3>判定示例</h3>
          <p>完整短句用于解释边界，不是必须命中的词语。</p>
          {examples.map((example, index) => (
            <article key={index} className="label-example">
              {editing ? (
                <>
                  <label>
                    原文表达
                    <textarea
                      aria-label={`示例原文 ${index + 1}`}
                      value={example.text}
                      onChange={(event) =>
                        updateExample(index, { text: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    是否适用
                    <select
                      aria-label={`示例判定 ${index + 1}`}
                      value={String(example.applies)}
                      onChange={(event) => {
                        const applies = event.target.value === "true";
                        updateExample(index, {
                          applies,
                          sentiment: applies ? label.allowed_sentiments[0] : null,
                        });
                      }}
                    >
                      <option value="true">适用</option>
                      <option value="false">不适用</option>
                    </select>
                  </label>
                  {example.applies && (
                    <label>
                      评价方向
                      <select
                        aria-label={`示例评价方向 ${index + 1}`}
                        value={example.sentiment ?? ""}
                        onChange={(event) =>
                          updateExample(index, { sentiment: event.target.value })
                        }
                      >
                        {label.allowed_sentiments.map((value) => (
                          <option key={value} value={value}>
                            {
                              { NEGATIVE: "负向", POSITIVE: "正向", NEUTRAL: "中性" }[
                                value
                              ]
                            }
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label>
                    判定说明
                    <textarea
                      aria-label={`示例说明 ${index + 1}`}
                      value={example.explanation}
                      onChange={(event) =>
                        updateExample(index, { explanation: event.target.value })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() =>
                      onChange({
                        examples: examples.filter((_, position) => position !== index),
                      })
                    }
                  >
                    删除示例 {index + 1}
                  </button>
                </>
              ) : (
                <>
                  <b>
                    {example.applies ? "适用" : "不适用"}
                    {example.sentiment &&
                      ` · ${{ NEGATIVE: "负向", POSITIVE: "正向", NEUTRAL: "中性" }[example.sentiment]}`}
                  </b>
                  <p>{example.text}</p>
                  <small>{example.explanation}</small>
                </>
              )}
            </article>
          ))}
          {editing && examples.length < 10 && (
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                onChange({
                  examples: [
                    ...examples,
                    {
                      text: "",
                      applies: true,
                      sentiment: label.allowed_sentiments[0],
                      explanation: "",
                    },
                  ],
                })
              }
            >
              增加示例
            </button>
          )}
        </div>
      )}
    </section>
  );
}
