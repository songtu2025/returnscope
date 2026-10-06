/** @typedef {import("./ClassificationStandardDraftEditor").ClassificationStandardEditorProps} EditorProps */
/** @typedef {Pick<EditorProps,"content"|"onChange"> & {fieldErrors: NonNullable<EditorProps["fieldErrors"]>, errorId: string}} BasicFieldsProps */
/** @param {BasicFieldsProps & {nameRef: import("react").Ref<HTMLInputElement>}} props */
function StandardName({ content, onChange, fieldErrors, errorId, nameRef }) {
  return (
    <label>
      标准名称
      <input
        ref={nameRef}
        aria-label="标准名称"
        aria-invalid={Boolean(fieldErrors.name)}
        aria-describedby={fieldErrors.name ? `${errorId}-name` : undefined}
        value={content.name}
        onChange={(event) => onChange({ ...content, name: event.target.value }, "name")}
      />
      {fieldErrors.name && (
        <span className="standard-field-error" id={`${errorId}-name`}>
          {fieldErrors.name}
        </span>
      )}
    </label>
  );
}
/** @param {BasicFieldsProps & {productContextRef: import("react").Ref<HTMLTextAreaElement>}} props */
function ProductContext({
  content,
  onChange,
  fieldErrors,
  errorId,
  productContextRef,
}) {
  return (
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
  );
}
/** @param {BasicFieldsProps & Pick<EditorProps,"section"|"editable"> & {nameRef: import("react").Ref<HTMLInputElement>, productContextRef: import("react").Ref<HTMLTextAreaElement>}} props */
export function StandardDraftBasicInformation({
  content,
  onChange,
  fieldErrors,
  errorId,
  nameRef,
  productContextRef,
  section,
  editable,
}) {
  return (
    <section className="standard-editor-section" hidden={section !== "settings"}>
      <header>
        <div>
          <h2>基本信息</h2>
        </div>
        <p>说明这套标准适用于什么商品。</p>
      </header>
      <fieldset disabled={!editable} className="standard-editor-fields two-columns">
        <StandardName
          content={content}
          onChange={onChange}
          fieldErrors={fieldErrors}
          errorId={errorId}
          nameRef={nameRef}
        />
        <ProductContext
          content={content}
          onChange={onChange}
          fieldErrors={fieldErrors}
          errorId={errorId}
          productContextRef={productContextRef}
        />
      </fieldset>
    </section>
  );
}
