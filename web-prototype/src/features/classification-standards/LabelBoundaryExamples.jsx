import { CLASSIFICATION_LABEL_SENTIMENTS as SENTIMENTS } from "./classificationLabelSentiments";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabelExample} ClassificationStandardEditableLabelExample */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSentiment} ClassificationStandardSentiment */
/** @typedef {{example: ClassificationStandardEditableLabelExample, index: number, label: ClassificationStandardEditableLabel, onUpdate: (change: Partial<ClassificationStandardEditableLabelExample>) => void, onRemove: () => void}} ExampleProps */

/** @param {string} value @returns {value is ClassificationStandardSentiment} */
function isSentiment(value) {
  return value === "NEGATIVE" || value === "POSITIVE" || value === "NEUTRAL";
}
/** @param {{title: string, name: string, value: string, onChange: (value: string) => void}} props */
function ExampleTextField({ title, name, value, onChange }) {
  return (
    <label>
      {title}
      <textarea
        aria-label={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
/** @param {ExampleProps} props */
function ExampleApplicability({ example, index, label, onUpdate }) {
  return (
    <label>
      是否适用
      <select
        aria-label={`示例判定 ${index + 1}`}
        value={String(example.applies)}
        onChange={(event) => {
          const applies = event.target.value === "true";
          onUpdate({
            applies,
            sentiment: applies ? label.allowed_sentiments[0] : null,
          });
        }}
      >
        <option value="true">适用</option>
        <option value="false">不适用</option>
      </select>
    </label>
  );
}
/** @param {ExampleProps} props */
function ExampleSentiment({ example, index, label, onUpdate }) {
  return (
    <>
      {example.applies && (
        <label>
          评价方向
          <select
            aria-label={`示例评价方向 ${index + 1}`}
            value={example.sentiment ?? ""}
            onChange={(event) => {
              const sentiment = event.target.value;
              if (isSentiment(sentiment)) {
                onUpdate({ sentiment });
              }
            }}
          >
            {label.allowed_sentiments.map((value) => (
              <option key={value} value={value}>
                {SENTIMENTS[value]}
              </option>
            ))}
          </select>
        </label>
      )}
    </>
  );
}
/** @param {ExampleProps} props */
function BoundaryExampleEditor(props) {
  const { example, index, onUpdate, onRemove } = props;
  return (
    <>
      <ExampleTextField
        title="原文表达"
        name={`示例原文 ${index + 1}`}
        value={example.text}
        onChange={(text) => onUpdate({ text })}
      />
      <ExampleApplicability {...props} />
      <ExampleSentiment {...props} />
      <ExampleTextField
        title="判定说明"
        name={`示例说明 ${index + 1}`}
        value={example.explanation}
        onChange={(explanation) => onUpdate({ explanation })}
      />
      <button type="button" className="secondary-button" onClick={onRemove}>
        删除示例 {index + 1}
      </button>
    </>
  );
}
/** @param {{example: ClassificationStandardEditableLabelExample}} props */
function BoundaryExampleView({ example }) {
  return (
    <>
      <b>
        {example.applies ? "适用" : "不适用"}
        {example.sentiment && ` · ${SENTIMENTS[example.sentiment]}`}
      </b>
      <p>{example.text}</p>
      <small>{example.explanation}</small>
    </>
  );
}
/** @param {ClassificationStandardEditableLabel} label @param {(change: Partial<ClassificationStandardEditableLabel>) => void} onChange */
function appendBoundaryExample(label, onChange) {
  /** @type {ClassificationStandardEditableLabelExample} */
  const example = {
    text: "",
    applies: true,
    sentiment: label.allowed_sentiments[0],
    explanation: "",
  };
  onChange({ examples: [...(label.examples ?? []), example] });
}

/** @param {import("./ClassificationLabelBoundaries").ClassificationLabelBoundariesProps} props */
export function LabelBoundaryExamples({ label, editing, onChange, onFieldRef }) {
  const examples = label.examples ?? [];
  /** @param {number} index @param {Partial<ClassificationStandardEditableLabelExample>} change */
  const updateExample = (index, change) =>
    onChange({
      examples: examples.map((item, position) =>
        position === index ? { ...item, ...change } : item,
      ),
    });
  return (
    <div tabIndex={-1} ref={(node) => onFieldRef("examples", node)}>
      <h3>判定示例</h3>
      <p>完整短句用于解释边界，不是必须命中的词语。</p>
      {examples.map((example, index) => (
        <article key={index} className="label-example">
          {editing ? (
            <BoundaryExampleEditor
              example={example}
              index={index}
              label={label}
              onUpdate={(change) => updateExample(index, change)}
              onRemove={() =>
                onChange({
                  examples: examples.filter((_, position) => position !== index),
                })
              }
            />
          ) : (
            <BoundaryExampleView example={example} />
          )}
        </article>
      ))}
      {editing && examples.length < 10 && (
        <button
          type="button"
          className="secondary-button"
          onClick={() => appendBoundaryExample(label, onChange)}
        >
          增加示例
        </button>
      )}
    </div>
  );
}
