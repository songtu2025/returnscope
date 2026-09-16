/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabelExample} ClassificationStandardEditableLabelExample */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSentiment} ClassificationStandardSentiment */

/** @type {Record<ClassificationStandardSentiment, string>} */
const SENTIMENTS = { NEGATIVE: "负向", POSITIVE: "正向", NEUTRAL: "中性" };

/**
 * @param {string} value
 * @returns {value is ClassificationStandardSentiment}
 */
function isSentiment(value) {
  return value === "NEGATIVE" || value === "POSITIVE" || value === "NEUTRAL";
}

/** @typedef {{label: ClassificationStandardEditableLabel, editing: boolean, onChange: (updates: Partial<ClassificationStandardEditableLabel>) => void, onFieldRef: (field: string, node: HTMLElement | null) => void}} ClassificationLabelBoundariesProps */

/** @param {ClassificationLabelBoundariesProps} props */
export function ClassificationLabelBoundaries({
  label,
  editing,
  onChange,
  onFieldRef,
}) {
  const exclusions = label.exclusions ?? [];
  const examples = label.examples ?? [];
  /**
   * @param {number} index
   * @param {Partial<ClassificationStandardEditableLabelExample>} change
   */
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
              ref={(node) => onFieldRef("exclusions", node)}
              rows={3}
              placeholder="每行说明一种不适用情况；避免重复判定说明"
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
        <div tabIndex={-1} ref={(node) => onFieldRef("examples", node)}>
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
                        onChange={(event) => {
                          const sentiment = event.target.value;
                          if (isSentiment(sentiment)) {
                            updateExample(index, { sentiment });
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
                    {example.sentiment && ` · ${SENTIMENTS[example.sentiment]}`}
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
              onClick={() => {
                /** @type {ClassificationStandardEditableLabelExample} */
                const example = {
                  text: "",
                  applies: true,
                  sentiment: label.allowed_sentiments[0],
                  explanation: "",
                };
                onChange({ examples: [...examples, example] });
              }}
            >
              增加示例
            </button>
          )}
        </div>
      )}
    </section>
  );
}
