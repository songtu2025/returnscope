import { Plus, Trash } from "@phosphor-icons/react";
/** @typedef {import("./ClassificationStandardDraftEditor").ClassificationStandardEditorProps} EditorProps */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVariant} ClassificationStandardVariant */
/** @typedef {Pick<EditorProps,"content"|"onChange"> & {fieldErrors: NonNullable<EditorProps["fieldErrors"]>, errorId: string, variantRefs: import("react").RefObject<Map<string, HTMLInputElement | null>>, updateVariant: (index: number, updates: Partial<ClassificationStandardVariant>) => void}} CategoryRowsProps */
/** @returns {ClassificationStandardVariant} */
const emptyVariant = () => ({ category_a: "", category_b: "", attributes: {} });
/** @param {{field: "category_a" | "category_b", title: string, variant: ClassificationStandardVariant, index: number, fieldErrors: NonNullable<EditorProps["fieldErrors"]>, errorId: string, variantRefs: import("react").RefObject<Map<string, HTMLInputElement | null>>, updateVariant: (index: number, updates: Partial<ClassificationStandardVariant>) => void}} props */
function CategoryField({
  field,
  title,
  variant,
  index,
  fieldErrors,
  errorId,
  variantRefs,
  updateVariant,
}) {
  const error = fieldErrors.variants?.[index]?.[field];
  const id = `${errorId}-variant-${index}-${field.replace("_", "-")}`;
  return (
    <label>
      品类 {title}
      <input
        ref={(node) => {
          variantRefs.current.set(`${index}.${field}`, node);
        }}
        aria-label={`品类 ${title} ${index + 1}`}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? id : undefined}
        value={variant[field]}
        onChange={(event) => updateVariant(index, { [field]: event.target.value })}
      />
      {error && (
        <span className="standard-field-error" id={id}>
          {error}
        </span>
      )}
    </label>
  );
}
/** @param {CategoryRowsProps & {variant: ClassificationStandardVariant, index: number}} props */
function CategoryRow({ content, onChange, variant, index, ...fields }) {
  return (
    <div>
      <CategoryField
        field="category_a"
        title="A"
        variant={variant}
        index={index}
        {...fields}
      />
      <CategoryField
        field="category_b"
        title="B"
        variant={variant}
        index={index}
        {...fields}
      />
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
  );
}
/** @param {Pick<EditorProps,"content"|"onChange"|"editable"> & {addVariantRef: import("react").Ref<HTMLButtonElement>}} props */
function AddCategoryButton({ content, onChange, editable, addVariantRef }) {
  return (
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
  );
}
/** @param {CategoryRowsProps & Pick<EditorProps,"section"|"editable"> & {addVariantRef: import("react").Ref<HTMLButtonElement>}} props */
export function StandardDraftCategories({
  content,
  onChange,
  fieldErrors,
  errorId,
  variantRefs,
  updateVariant,
  section,
  editable,
  addVariantRef,
}) {
  return (
    <section className="standard-editor-section" hidden={section !== "settings"}>
      <header>
        <div>
          <h2>适用品类</h2>
        </div>
        <AddCategoryButton
          content={content}
          onChange={onChange}
          editable={editable}
          addVariantRef={addVariantRef}
        />
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
          <CategoryRow
            key={index}
            content={content}
            onChange={onChange}
            variant={variant}
            index={index}
            fieldErrors={fieldErrors}
            errorId={errorId}
            variantRefs={variantRefs}
            updateVariant={updateVariant}
          />
        ))}
      </fieldset>
    </section>
  );
}
