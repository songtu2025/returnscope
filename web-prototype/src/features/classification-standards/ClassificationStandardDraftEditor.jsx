import { useState } from "react";
import { ClassificationLabelWorkbench } from "./ClassificationLabelWorkbench";
import { Plus, Trash } from "@phosphor-icons/react";

const emptyVariant = () => ({ category_a: "", category_b: "", attributes: {} });

export function ClassificationStandardEditor({
  content,
  baseContent,
  onChange,
  focusLabelCode,
  section,
  savedContent,
  busy,
  editable,
  initiallyEditing,
  notify,
}) {
  const [partCode, setPartCode] = useState("");
  const updateVariant = (index, updates) => {
    onChange({
      ...content,
      variants: content.variants.map((variant, itemIndex) =>
        itemIndex === index ? { ...variant, ...updates } : variant,
      ),
    });
  };

  const addPart = () => {
    const normalized = partCode.trim().toUpperCase();
    if (!normalized || content.allowed_parts.includes(normalized)) return;
    onChange({
      ...content,
      allowed_parts: [...content.allowed_parts, normalized],
    });
    setPartCode("");
  };

  return (
    <fieldset
      className="standard-editor-stack"
      disabled={busy}
      aria-label="标准草稿编辑"
    >
      <section className="standard-editor-section" hidden={section !== "settings"}>
        <header>
          <div>
            <h2>基本信息</h2>
          </div>
          <p>说明这套标准适用于什么商品。</p>
        </header>
        <fieldset disabled={!editable} className="standard-editor-fields two-columns">
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
        </fieldset>
      </section>

      <section className="standard-editor-section" hidden={section !== "settings"}>
        <header>
          <div>
            <h2>适用品类</h2>
          </div>
          <button
            type="button"
            className="secondary-button compact-button"
            disabled={!editable}
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
        <fieldset className="standard-category-rows" disabled={!editable}>
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
        </fieldset>
      </section>

      <div hidden={section !== "labels"}>
        <ClassificationLabelWorkbench
          content={content}
          baseContent={baseContent}
          savedContent={savedContent}
          onChange={onChange}
          focusLabelCode={focusLabelCode}
          busy={busy}
          editable={editable}
          initiallyEditing={initiallyEditing}
          notify={notify}
        />
      </div>

      <details className="standard-advanced-settings" hidden={section !== "settings"}>
        <summary>高级分类设置</summary>
        <fieldset disabled={!editable}>
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
              {content.allowed_parts.map((value) => (
                <label key={value}>
                  <input
                    type="checkbox"
                    checked
                    disabled={value === "UNSPECIFIED"}
                    onChange={() => {
                      onChange({
                        ...content,
                        allowed_parts: content.allowed_parts.filter(
                          (item) => item !== value,
                        ),
                      });
                    }}
                  />
                  <span>{value === "UNSPECIFIED" ? "未指定部位" : value}</span>
                  <code>{value}</code>
                </label>
              ))}
            </div>
            <div className="standard-part-entry">
              <input
                aria-label="新增证据部位编码"
                placeholder="例如 PALM"
                value={partCode}
                onChange={(event) => setPartCode(event.target.value)}
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
          </fieldset>
        </fieldset>
      </details>
    </fieldset>
  );
}
