import { Plus } from "@phosphor-icons/react";
/** @typedef {import("./ClassificationStandardDraftEditor").ClassificationStandardEditorProps} EditorProps */
/** @typedef {Pick<EditorProps,"content"|"onChange">} AdvancedContentProps */
/** @param {AdvancedContentProps} props */
function DraftInstructions({ content, onChange }) {
  return (
    <label>
      补充判断说明
      <textarea
        rows={4}
        value={content.instructions.join("\n")}
        onChange={(event) =>
          onChange({
            ...content,
            instructions: event.target.value.split("\n"),
          })
        }
      />
    </label>
  );
}
/** @param {AdvancedContentProps} props */
function PartOptions({ content, onChange }) {
  return (
    <div className="standard-part-options">
      {content.allowed_parts.map((value) => (
        <label key={value}>
          <input
            type="checkbox"
            checked
            disabled={value === "UNSPECIFIED"}
            onChange={() => {
              onChange({
                ...content,
                allowed_parts: content.allowed_parts.filter((item) => item !== value),
              });
            }}
          />
          <span>{value === "UNSPECIFIED" ? "未指定部位" : value}</span>
          <code>{value}</code>
        </label>
      ))}
    </div>
  );
}
/** @typedef {{partCodeRef: import("react").Ref<HTMLInputElement>, partCode: string, partError: string, errorId: string, setPartCode: (value: string) => void, setPartError: (value: string) => void, addPart: () => void}} PartEntryProps */
/** @param {PartEntryProps} props */
function PartEntry({
  partCodeRef,
  partCode,
  partError,
  errorId,
  setPartCode,
  setPartError,
  addPart,
}) {
  return (
    <>
      <div className="standard-part-entry">
        <input
          ref={partCodeRef}
          aria-label="新增证据部位编码"
          aria-invalid={Boolean(partError)}
          aria-describedby={partError ? `${errorId}-part-code` : undefined}
          placeholder="例如 PALM"
          value={partCode}
          onChange={(event) => {
            setPartCode(event.target.value);
            setPartError("");
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            addPart();
          }}
        />
        <button type="button" className="secondary-button" onClick={addPart}>
          <Plus size={15} /> 新增部位
        </button>
      </div>
      {partError && (
        <p className="standard-field-error" id={`${errorId}-part-code`}>
          {partError}
        </p>
      )}
    </>
  );
}
/** @param {AdvancedContentProps & PartEntryProps & Pick<EditorProps,"section"|"editable">} props */
export function StandardDraftAdvancedSettings({
  content,
  onChange,
  section,
  editable,
  ...entry
}) {
  return (
    <details className="standard-advanced-settings" hidden={section !== "settings"}>
      <summary>高级分类设置</summary>
      <fieldset disabled={!editable}>
        <p>通常无需修改。这里控制智能体的补充判断说明和可输出证据部位。</p>
        <DraftInstructions content={content} onChange={onChange} />
        <fieldset>
          <legend>可识别证据部位</legend>
          <PartOptions content={content} onChange={onChange} />
          <PartEntry {...entry} />
        </fieldset>
      </fieldset>
    </details>
  );
}
