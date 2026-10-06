import { X } from "@phosphor-icons/react";
/** @typedef {import("./ClassificationLabelWorkbench").ClassificationLabelWorkbenchProps} WorkbenchProps */
/** @typedef {ReturnType<typeof import("./useClassificationLabelWorkbenchController").useClassificationLabelWorkbenchController>} Controller */
/** @typedef {Pick<Controller,"editing"|"updateLabel"> & Pick<WorkbenchProps,"editable"> & {label: NonNullable<Controller["label"]>}} KeywordTokensProps */
/** @param {KeywordTokensProps} props */
function KeywordTokens({ label, editable, editing, updateLabel }) {
  return (
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
                  keywords: label.keywords.filter((_word, i) => i !== index),
                })
              }
            >
              <X size={13} />
            </button>
          )}
        </span>
      ))}
    </div>
  );
}
/** @typedef {Pick<Controller,"keywordText"|"setKeywordText"|"commitKeywords"> & {entry: NonNullable<Controller["entry"]>}} KeywordInputProps */
/** @param {KeywordInputProps} props */
function KeywordInput({ entry, keywordText, setKeywordText, commitKeywords }) {
  return (
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
  );
}
/** @param {KeywordTokensProps & KeywordInputProps & Pick<WorkbenchProps,"content">} props */
export function LabelKeywordEditor({
  label,
  editable,
  editing,
  updateLabel,
  entry,
  keywordText,
  setKeywordText,
  commitKeywords,
  content,
}) {
  return (
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

      <KeywordTokens
        label={label}
        editable={editable}
        editing={editing}
        updateLabel={updateLabel}
      />
      {editable && editing && (
        <KeywordInput
          entry={entry}
          keywordText={keywordText}
          setKeywordText={setKeywordText}
          commitKeywords={commitKeywords}
        />
      )}
      {!label.keywords?.length && !editing && <p>未配置搜索别名。</p>}
    </details>
  );
}
