import { Plus, Trash } from "@phosphor-icons/react";

const PART_OPTIONS = [
  ["UNSPECIFIED", "未指定部位"],
  ["FRAME", "镜框"],
  ["LENS", "镜片"],
  ["TEMPLE", "镜腿"],
  ["BRIDGE", "鼻梁"],
  ["HEEL", "后跟"],
  ["TOE", "鞋头"],
  ["SOLE", "鞋底"],
  ["UPPER", "鞋面"],
  ["CUFF", "袖口"],
  ["CROWN", "帽身"],
  ["BRIM", "帽檐"],
];

const emptyVariant = () => ({ category_a: "", category_b: "", attributes: {} });

const emptyLabel = () => ({
  code: "",
  name: "",
  group: "",
  description: "",
  keywords: [],
  allowed_sentiments: ["NEGATIVE"],
});

export function ClassificationStandardEditor({ content, baseContent, onChange }) {
  const publishedCodes = new Set(
    (baseContent?.labels ?? []).map((label) => label.code),
  );

  const updateVariant = (index, updates) => {
    onChange({
      ...content,
      variants: content.variants.map((variant, itemIndex) =>
        itemIndex === index ? { ...variant, ...updates } : variant,
      ),
    });
  };

  const updateLabel = (index, updates) => {
    onChange({
      ...content,
      labels: content.labels.map((label, itemIndex) =>
        itemIndex === index ? { ...label, ...updates } : label,
      ),
    });
  };

  return (
    <div className="standard-editor-stack">
      <section className="standard-editor-section">
        <header>
          <div>
            <span>01</span>
            <h2>基本信息</h2>
          </div>
          <p>说明这套标准适用于什么商品。</p>
        </header>
        <div className="standard-editor-fields two-columns">
          <label>
            标准名称
            <input
              aria-label="标准名称"
              value={content.name}
              onChange={(event) => onChange({ ...content, name: event.target.value })}
            />
          </label>
          <label className="wide-field">
            适用商品说明
            <textarea
              aria-label="适用商品说明"
              rows={3}
              value={content.product_context}
              onChange={(event) =>
                onChange({ ...content, product_context: event.target.value })
              }
            />
          </label>
        </div>
      </section>

      <section className="standard-editor-section">
        <header>
          <div>
            <span>02</span>
            <h2>适用品类</h2>
          </div>
          <button
            type="button"
            className="secondary-button compact-button"
            onClick={() =>
              onChange({ ...content, variants: [...content.variants, emptyVariant()] })
            }
          >
            <Plus size={15} /> 增加品类
          </button>
        </header>
        <p className="standard-section-help">
          商品主数据中的品类 A 与品类 B 会据此匹配分类标准。
        </p>
        <div className="standard-category-rows">
          {content.variants.map((variant, index) => (
            <div key={index}>
              <label>
                品类 A
                <input
                  aria-label={`品类 A ${index + 1}`}
                  value={variant.category_a}
                  onChange={(event) =>
                    updateVariant(index, { category_a: event.target.value })
                  }
                />
              </label>
              <label>
                品类 B
                <input
                  aria-label={`品类 B ${index + 1}`}
                  value={variant.category_b}
                  onChange={(event) =>
                    updateVariant(index, { category_b: event.target.value })
                  }
                />
              </label>
              <button
                type="button"
                className="icon-button"
                aria-label={`删除品类 ${index + 1}`}
                disabled={content.variants.length === 1}
                onClick={() =>
                  onChange({
                    ...content,
                    variants: content.variants.filter(
                      (_item, itemIndex) => itemIndex !== index,
                    ),
                  })
                }
              >
                <Trash size={16} />
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="standard-editor-section">
        <header>
          <div>
            <span>03</span>
            <h2>分类标签体系</h2>
          </div>
          <button
            type="button"
            className="secondary-button compact-button"
            onClick={() =>
              onChange({ ...content, labels: [...content.labels, emptyLabel()] })
            }
          >
            <Plus size={15} /> 增加标签
          </button>
        </header>
        <p className="standard-section-help">
          标签定义是智能体判断退货原因的直接依据。已发布标签的编码不可修改。
        </p>
        {content.labels.length === 0 ? (
          <div className="standard-editor-empty">至少增加一个分类标签。</div>
        ) : (
          <div className="standard-label-editor-list">
            {content.labels.map((label, index) => (
              <article key={index}>
                <div className="standard-label-editor-heading">
                  <strong>{label.name || `新标签 ${index + 1}`}</strong>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`删除标签 ${label.name || index + 1}`}
                    onClick={() =>
                      onChange({
                        ...content,
                        labels: content.labels.filter(
                          (_item, itemIndex) => itemIndex !== index,
                        ),
                      })
                    }
                  >
                    <Trash size={16} />
                  </button>
                </div>
                <div className="standard-editor-fields label-fields">
                  <label>
                    标签分组
                    <input
                      aria-label={`标签分组 ${index + 1}`}
                      value={label.group}
                      onChange={(event) =>
                        updateLabel(index, { group: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    标签名称
                    <input
                      aria-label={`标签名称 ${index + 1}`}
                      value={label.name}
                      onChange={(event) =>
                        updateLabel(index, { name: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    标签编码
                    <input
                      aria-label={`标签编码 ${index + 1}`}
                      disabled={publishedCodes.has(label.code)}
                      placeholder="例如 FIT_TOO_SMALL"
                      value={label.code}
                      onChange={(event) =>
                        updateLabel(index, { code: event.target.value.toUpperCase() })
                      }
                    />
                  </label>
                  <label className="wide-field">
                    业务定义
                    <textarea
                      aria-label={`业务定义 ${index + 1}`}
                      rows={2}
                      value={label.description}
                      onChange={(event) =>
                        updateLabel(index, { description: event.target.value })
                      }
                    />
                  </label>
                  <label className="wide-field">
                    英文关键词
                    <input
                      aria-label={`英文关键词 ${index + 1}`}
                      placeholder="多个关键词用逗号分隔"
                      value={(label.keywords ?? []).join(", ")}
                      onChange={(event) =>
                        updateLabel(index, {
                          keywords: event.target.value
                            .split(",")
                            .map((value) => value.trimStart()),
                        })
                      }
                    />
                  </label>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <details className="standard-advanced-settings">
        <summary>高级分类设置</summary>
        <p>通常无需修改。这里控制智能体的补充判断说明和可输出证据部位。</p>
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
        <fieldset>
          <legend>可识别证据部位</legend>
          <div className="standard-part-options">
            {PART_OPTIONS.map(([value, label]) => (
              <label key={value}>
                <input
                  type="checkbox"
                  checked={content.allowed_parts.includes(value)}
                  disabled={value === "UNSPECIFIED"}
                  onChange={() => {
                    const selected = content.allowed_parts.includes(value);
                    onChange({
                      ...content,
                      allowed_parts: selected
                        ? content.allowed_parts.filter((item) => item !== value)
                        : [...content.allowed_parts, value],
                    });
                  }}
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </details>
    </div>
  );
}
