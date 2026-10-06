import { useEffect, useId, useRef, useState } from "react";
import { ClassificationLabelWorkbench } from "./ClassificationLabelWorkbench";
import { ClassificationHierarchyEditor } from "./ClassificationHierarchyEditor";
import { StandardDraftBasicInformation } from "./StandardDraftBasicInformation";
import { StandardDraftCategories } from "./StandardDraftCategories";
import { StandardDraftAdvancedSettings } from "./StandardDraftAdvancedSettings";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVariant} ClassificationStandardVariant */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, section: string, savedContent: ClassificationStandardEditableContent | null, busy: boolean, editable: boolean, initiallyEditing: boolean, notify: (message: string, tone?: string) => void, fieldErrors?: Partial<ClassificationStandardFieldErrors>, validationAttempt?: number}} ClassificationStandardEditorProps */

/** @param {Partial<ClassificationStandardFieldErrors>} fieldErrors @param {Map<string, HTMLInputElement | null>} refs */
function firstVariantErrorTarget(fieldErrors, refs) {
  const index = fieldErrors.variants?.findIndex(
    (item) => item.category_a || item.category_b,
  );
  if (index == null || index < 0 || !fieldErrors.variants) return null;
  const key = fieldErrors.variants[index]?.category_a ? "category_a" : "category_b";
  return refs.get(`${index}.${key}`) ?? null;
}

/** @param {ClassificationStandardEditorProps} props */
export function ClassificationStandardEditor({
  content,
  baseContent,
  onChange,
  focusLabelCode,
  fixRequest,
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
  const editorRef = useRef(/** @type {HTMLFieldSetElement | null} */ (null));
  const nameRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const productContextRef = useRef(/** @type {HTMLTextAreaElement | null} */ (null));
  const addVariantRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const partCodeRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const variantRefs = useRef(
    /** @type {Map<string, HTMLInputElement | null>} */ (new Map()),
  );
  const focusedAttemptRef = useRef(0);

  useEffect(() => {
    if (!fixRequest || fixRequest.label_code || fixRequest.label_index != null) return;
    if (fixRequest.kind === "invalid_structure") {
      const hierarchy = editorRef.current?.querySelector(".hierarchy-category-editor");
      if (hierarchy) {
        if (hierarchy instanceof HTMLDetailsElement) hierarchy.open = true;
        hierarchy.querySelector("summary")?.focus();
      }
    } else if (fixRequest.kind === "missing_field") {
      const target =
        fixRequest.field === "name" ? nameRef.current : productContextRef.current;
      target?.focus();
    }
  }, [fixRequest, section]);

  /**
   * @param {number} index
   * @param {Partial<ClassificationStandardVariant>} updates
   */
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
    /** @type {HTMLElement | null} */
    let target = null;
    if (fieldErrors.name) target = nameRef.current;
    else if (fieldErrors.product_context) target = productContextRef.current;
    else if (fieldErrors.variants_empty) target = addVariantRef.current;
    else target = firstVariantErrorTarget(fieldErrors, variantRefs.current);
    if (target) {
      focusedAttemptRef.current = validationAttempt;
      target.focus();
    }
  }, [busy, fieldErrors, section, validationAttempt]);

  return (
    <fieldset
      ref={editorRef}
      className="standard-editor-stack"
      disabled={Boolean(busy)}
      aria-label="标准草稿编辑"
    >
      <StandardDraftBasicInformation
        content={content}
        onChange={onChange}
        fieldErrors={fieldErrors}
        errorId={errorId}
        nameRef={nameRef}
        productContextRef={productContextRef}
        section={section}
        editable={editable}
      />
      <StandardDraftCategories
        content={content}
        onChange={onChange}
        fieldErrors={fieldErrors}
        errorId={errorId}
        variantRefs={variantRefs}
        updateVariant={updateVariant}
        section={section}
        editable={editable}
        addVariantRef={addVariantRef}
      />
      <div hidden={section !== "labels"}>
        {content.structure_version === 2 && (
          <ClassificationHierarchyEditor
            content={content}
            onChange={onChange}
            disabled={busy || !editable}
          />
        )}
        <ClassificationLabelWorkbench
          content={content}
          baseContent={baseContent}
          savedContent={savedContent}
          onChange={onChange}
          focusLabelCode={focusLabelCode}
          fixRequest={fixRequest}
          busy={busy}
          editable={editable}
          initiallyEditing={initiallyEditing}
          notify={notify}
          fieldErrors={fieldErrors}
          validationAttempt={validationAttempt}
          section={section}
        />
      </div>

      <StandardDraftAdvancedSettings
        content={content}
        onChange={onChange}
        section={section}
        editable={editable}
        partCodeRef={partCodeRef}
        partCode={partCode}
        partError={partError}
        errorId={errorId}
        setPartCode={setPartCode}
        setPartError={setPartError}
        addPart={addPart}
      />
    </fieldset>
  );
}
