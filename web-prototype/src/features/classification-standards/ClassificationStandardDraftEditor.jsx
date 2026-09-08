import { useEffect, useId, useRef, useState } from "react";
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
  fieldErrors = {},
  validationAttempt = 0,
}) {
  const [partCode, setPartCode] = useState("");
  const [partError, setPartError] = useState("");
  const errorId = useId();
  const nameRef = useRef(null);
  const productContextRef = useRef(null);
  const addVariantRef = useRef(null);
  const partCodeRef = useRef(null);
  const variantRefs = useRef(new Map());
  const focusedAttemptRef = useRef(0);

  const updateVariant = (index, updates) => {
    const field = Object.keys(updates)[0];
    onChange(
      {
        ...content,
        variants: content.variants.map((variant, itemIndex) =>
          itemIndex === index ? { ...variant, ...updates } : variant,
        ),
      },
      `variants.${index}.${field}`,
    );
  };

  const addPart = () => {
    const normalized = partCode.trim().toUpperCase();
    if (!normalized) {
      setPartError("请输入证据部位编码");
      partCodeRef.current?.focus();
      return;
    }
    if (content.allowed_parts.includes(normalized)) return;
    onChange({
      ...content,
      allowed_parts: [...content.allowed_parts, normalized],
    });
    setPartCode("");
  };

  useEffect(() => {
    if (
      !validationAttempt ||
      busy ||
      section !== "settings" ||
      focusedAttemptRef.current === validationAttempt
    ) {
      return;
    }
    let target = null;
    if (fieldErrors.name) target = nameRef.current;
    else if (fieldErrors.product_context) target = productContextRef.current;
    else if (fieldErrors.variants_empty) target = addVariantRef.current;
    else {
      const index = fieldErrors.variants?.findIndex(
        (item) => item.category_a || item.category_b,
      );
      if (index >= 0) {
        const key = fieldErrors.variants[index].category_a
          ? "category_a"
          : "category_b";
        target = variantRefs.current.get(`${index}.${key}`);
      }
    }
    if (target) {
      focusedAttemptRef.current = validationAttempt;
      target.focus();
    }
  }, [busy, fieldErrors, section, validationAttempt]);

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
              ref={nameRef}
              aria-label="标准名称"
              aria-invalid={Boolean(fieldErrors.name)}
              aria-describedby={fieldErrors.name ? `${errorId}-name` : undefined}
              value={content.name}
              onChange={(event) =>
                onChange({ ...content, name: event.target.value }, "name")
              }
            />
            {fieldErrors.name && (
              <span className="standard-field-error" id={`${errorId}-name`}>
                {fieldErrors.name}
              </span>
            )}
          </label>
          <label className="wide-field">
            适用商品说明
            <textarea
              ref={productContextRef}
              aria-label="适用商品说明"
              aria-invalid={Boolean(fieldErrors.product_context)}
              aria-describedby={
                fieldErrors.product_context ? `${errorId}-product-context` : undefined
              }
              rows={3}
              value={content.product_context}
              onChange={(event) =>
                onChange(
                  { ...content, product_context: event.target.value },
                  "product_context",
                )
              }
            />
            {fieldErrors.product_context && (
              <span className="standard-field-error" id={`${errorId}-product-context`}>
                {fieldErrors.product_context}
              </span>
            )}
          </label>
        </fieldset>
      </section>

      <section className="standard-editor-section" hidden={section !== "settings"}>
        <header>
          <div>
            <h2>适用品类</h2>
          </div>
          <button
            ref={addVariantRef}
            type="button"
            className="secondary-button compact-button"
            disabled={!editable}
            onClick={() =>
              onChange(
                { ...content, variants: [...content.variants, emptyVariant()] },
                "variants_empty",
              )
            }
          >
            <Plus size={15} /> 增加品类
          </button>
        </header>
        <p className="standard-section-help">
          商品主数据中的品类 A 与品类 B 会据此匹配分类标准。
        </p>
        {fieldErrors.variants_empty && (
          <p className="standard-field-error" id={`${errorId}-variants`}>
            {fieldErrors.variants_empty}
          </p>
        )}
        <fieldset className="standard-category-rows" disabled={!editable}>
          {content.variants.map((variant, index) => (
            <div key={index}>
              <label>
                品类 A
                <input
                  ref={(node) => {
                    variantRefs.current.set(`${index}.category_a`, node);
                  }}
                  aria-label={`品类 A ${index + 1}`}
                  aria-invalid={Boolean(fieldErrors.variants?.[index]?.category_a)}
                  aria-describedby={
                    fieldErrors.variants?.[index]?.category_a
                      ? `${errorId}-variant-${index}-category-a`
                      : undefined
                  }
                  value={variant.category_a}
                  onChange={(event) =>
                    updateVariant(index, { category_a: event.target.value })
                  }
                />
                {fieldErrors.variants?.[index]?.category_a && (
                  <span
                    className="standard-field-error"
                    id={`${errorId}-variant-${index}-category-a`}
                  >
                    {fieldErrors.variants[index].category_a}
                  </span>
                )}
              </label>
              <label>
                品类 B
                <input
                  ref={(node) => {
                    variantRefs.current.set(`${index}.category_b`, node);
                  }}
                  aria-label={`品类 B ${index + 1}`}
                  aria-invalid={Boolean(fieldErrors.variants?.[index]?.category_b)}
                  aria-describedby={
                    fieldErrors.variants?.[index]?.category_b
                      ? `${errorId}-variant-${index}-category-b`
                      : undefined
                  }
                  value={variant.category_b}
                  onChange={(event) =>
                    updateVariant(index, { category_b: event.target.value })
                  }
                />
                {fieldErrors.variants?.[index]?.category_b && (
                  <span
                    className="standard-field-error"
                    id={`${errorId}-variant-${index}-category-b`}
                  >
                    {fieldErrors.variants[index].category_b}
                  </span>
                )}
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
          fieldErrors={fieldErrors}
          validationAttempt={validationAttempt}
          section={section}
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
          </fieldset>
        </fieldset>
      </details>
    </fieldset>
  );
}
