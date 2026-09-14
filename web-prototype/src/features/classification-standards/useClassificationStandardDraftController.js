import { useCallback, useEffect, useRef, useState } from "react";

import { navigateHash } from "../../app/hashRouter";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  classificationStandardContentFieldErrors,
  clearClassificationStandardContentFieldError,
  cloneClassificationStandardContent,
  contentFromClassificationStandardSnapshot,
  EMPTY_CLASSIFICATION_STANDARD_CONTENT,
  validateClassificationStandardContent,
} from "./classificationStandardContent";
import { useClassificationStandardValidationController } from "./useClassificationStandardValidationController";

/** @typedef {"legacy_v3" | "semantic_v1" | "fact_v2" | "keyword_free_v1"} RecognitionProfile */
/** @typedef {"legacy_v3" | "semantic_v1" | "fact_v2"} WritableRecognitionProfile */
/** @typedef {"NEGATIVE" | "POSITIVE" | "NEUTRAL"} SentimentCode */
/** @typedef {{category_a: string, category_b: string, attributes: Record<string, string>}} ClassificationStandardVariant */
/** @typedef {{text: string, applies: boolean, sentiment: SentimentCode | null, explanation: string}} LabelExample */
/**
 * @typedef {object} ClassificationStandardLabel
 * @property {string} code
 * @property {string} name
 * @property {string} group
 * @property {string | null} [parent_code]
 * @property {string} description
 * @property {string[]} keywords
 * @property {string[]} exclusions
 * @property {LabelExample[]} examples
 * @property {SentimentCode[]} allowed_sentiments
 * @property {string[]} allowed_claim_ids
 */
/**
 * @typedef {object} ClassificationStandardSnapshot
 * @property {string} name
 * @property {ClassificationStandardVariant[]} [variants]
 * @property {Record<string, unknown>[]} [import_sources]
 * @property {{
 *   product_context: string,
 *   recognition_profile?: RecognitionProfile,
 *   instructions?: string[],
 *   allowed_parts?: string[],
 *   validation_rules?: Record<string, unknown>,
 *   structure_version?: 1 | 2,
 *   categories?: Record<string, unknown>[],
 *   labels?: Record<string, unknown>[],
 * }} taxonomy
 */
/**
 * @typedef {object} ClassificationStandardContent
 * @property {RecognitionProfile} recognition_profile
 * @property {string} name
 * @property {string} product_context
 * @property {string[]} instructions
 * @property {string[]} allowed_parts
 * @property {Record<string, unknown>} validation_rules
 * @property {ClassificationStandardVariant[]} variants
 * @property {ClassificationStandardLabel[]} labels
 * @property {1 | 2} [structure_version]
 * @property {Record<string, unknown>[]} [categories]
 * @property {Record<string, unknown>[]} [import_sources]
 */
/** @typedef {Omit<ClassificationStandardContent, "recognition_profile"> & {recognition_profile: WritableRecognitionProfile}} WritableClassificationStandardContent */
/**
 * @typedef {object} ClassificationStandardFieldErrors
 * @property {string} name
 * @property {string} product_context
 * @property {{category_a: string, category_b: string}[]} variants
 * @property {string} variants_empty
 * @property {{name: string, group: string, code: string}[]} labels
 * @property {string} labels_empty
 */
/** @typedef {{id: string, version_no: number, version_reason: string, published_at: string}} ClassificationStandardVersion */
/**
 * @typedef {object} ClassificationStandardDetail
 * @property {string} id
 * @property {string} name
 * @property {string | null} draft_id
 * @property {string} standard_version_id
 * @property {ClassificationStandardSnapshot} snapshot
 */
/**
 * @typedef {object} ClassificationStandardDraft
 * @property {string} id
 * @property {string} standard_id
 * @property {number} base_version_no
 * @property {number} revision
 * @property {boolean} is_new
 * @property {string} change_reason
 * @property {ClassificationStandardContent} content
 * @property {ClassificationStandardSnapshot} snapshot
 * @property {ClassificationStandardSnapshot} base_snapshot
 * @property {{
 *   blocking: string[],
 *   warnings: string[],
 *   issues: {
 *     kind: string,
 *     message: string,
 *     field: string | null,
 *     label_code?: string,
 *     label_index?: number,
 *   }[],
 * }} validation
 */

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/**
 * @param {ClassificationStandardContent} content
 * @returns {WritableClassificationStandardContent}
 */
function writableClassificationStandardContent(content) {
  if (content.recognition_profile === "keyword_free_v1") {
    throw new Error("keyword_free_v1 识别模式仅支持读取");
  }
  return { ...content, recognition_profile: content.recognition_profile };
}

/**
 * @param {{
 *   mode: string,
 *   selectedId: string,
 *   notify: (message: string, tone?: string) => void,
 *   loadStandards: () => Promise<unknown[]>,
 *   setBusy: (busy: string) => void,
 * }} options
 */
export function useClassificationStandardDraftController({
  mode,
  selectedId,
  notify,
  loadStandards,
  setBusy,
}) {
  const [detail, setDetail] = useState(
    /** @type {ClassificationStandardDetail | null} */ (null),
  );
  const [versions, setVersions] = useState(
    /** @type {ClassificationStandardVersion[]} */ ([]),
  );
  const [draft, setDraft] = useState(
    /** @type {ClassificationStandardDraft | null} */ (null),
  );
  const [content, setContent] = useState(
    /** @type {ClassificationStandardContent} */ (
      cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT)
    ),
  );
  const [changeReason, setChangeReason] = useState("");
  const [pageLoading, setPageLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState(
    /** @type {Partial<ClassificationStandardFieldErrors>} */ ({}),
  );
  const [validationAttempt, setValidationAttempt] = useState(0);
  const loadGenerationRef = useRef(0);

  const validation = useClassificationStandardValidationController({
    draft,
    notify,
    persistDraft,
    setBusy,
  });
  const {
    validationSources,
    validationRuns,
    selectedValidation,
    validationSourceId,
    validationSampleSize,
    setValidationSourceId,
    setValidationSampleSize,
    loadValidation,
    clearValidation,
    startSampleValidation,
    approveSampleValidation,
    selectValidation,
  } = validation;

  function requireDetail() {
    if (!detail) throw new Error("当前分类标准不存在");
    return detail;
  }

  const loadSelected = useCallback(
    async (/** @type {string} */ standardId) => {
      const generation = ++loadGenerationRef.current;
      setPageLoading(true);
      try {
        /** @type {[ClassificationStandardDetail, ClassificationStandardVersion[]]} */
        const [standard, versionRows] = await Promise.all([
          classificationStandardApi.classificationStandard(standardId),
          classificationStandardApi.classificationStandardVersions(standardId),
        ]);
        /** @type {ClassificationStandardDraft | null} */
        const draftValue = standard.draft_id
          ? await classificationStandardApi.classificationStandardDraft(
              standard.draft_id,
            )
          : null;
        if (generation !== loadGenerationRef.current) return;
        setDetail(standard);
        setVersions(versionRows);
        setDraft(draftValue);
        setContent(
          cloneClassificationStandardContent(
            draftValue?.content ??
              contentFromClassificationStandardSnapshot(standard.snapshot),
          ),
        );
        setFieldErrors({});
        setChangeReason(draftValue?.change_reason || `更新${standard.name}`);
        if (draftValue) await loadValidation(draftValue.id);
        else clearValidation();
      } catch (error) {
        if (generation === loadGenerationRef.current) throw error;
      } finally {
        if (generation === loadGenerationRef.current) setPageLoading(false);
      }
    },
    [clearValidation, loadValidation],
  );

  useEffect(() => {
    if (mode === "new") {
      loadGenerationRef.current += 1;
      setPageLoading(false);
      clearValidation();
      setDetail(null);
      setVersions([]);
      setDraft(null);
      setContent(
        cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT),
      );
      setFieldErrors({});
      setChangeReason("新增分类标准");
      return undefined;
    }
    if (!selectedId) {
      loadGenerationRef.current += 1;
      setPageLoading(false);
      clearValidation();
      return undefined;
    }
    loadSelected(selectedId).catch((error) => notify(errorMessage(error), "error"));
    return () => {
      loadGenerationRef.current += 1;
    };
  }, [clearValidation, loadSelected, mode, notify, selectedId]);

  const savedContent =
    draft?.content ??
    (detail?.snapshot
      ? contentFromClassificationStandardSnapshot(detail.snapshot)
      : EMPTY_CLASSIFICATION_STANDARD_CONTENT);
  const dirty = JSON.stringify(content) !== JSON.stringify(savedContent);

  useEffect(() => {
    if (!dirty || !["edit", "new"].includes(mode)) return;
    const warnBeforeClose = (/** @type {BeforeUnloadEvent} */ event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeClose);
    return () => window.removeEventListener("beforeunload", warnBeforeClose);
  }, [dirty, mode]);

  /** @returns {Promise<ClassificationStandardDraft>} */
  async function persistDraft() {
    const error = validateClassificationStandardContent(content);
    if (error) {
      setFieldErrors(classificationStandardContentFieldErrors(content));
      setValidationAttempt((value) => value + 1);
      throw new Error(error);
    }
    const writableContent = writableClassificationStandardContent(content);
    setFieldErrors({});

    let workingDraft = draft;
    if (!workingDraft) {
      if (mode === "new") {
        const firstCategory = content.variants[0];
        /** @type {ClassificationStandardDraft} */
        const createdDraft =
          await classificationStandardApi.createClassificationStandard({
            name: content.name.trim(),
            product_context: content.product_context.trim(),
            category_a: firstCategory.category_a.trim(),
            category_b: firstCategory.category_b.trim(),
          });
        workingDraft = createdDraft;
      } else {
        /** @type {ClassificationStandardDraft} */
        const createdDraft =
          await classificationStandardApi.createClassificationStandardDraft(
            requireDetail().id,
          );
        workingDraft = createdDraft;
      }
    }

    if (JSON.stringify(writableContent) !== JSON.stringify(workingDraft.content)) {
      /** @type {ClassificationStandardDraft} */
      const updatedDraft =
        await classificationStandardApi.updateClassificationStandardDraft(
          workingDraft.id,
          {
            expected_revision: workingDraft.revision,
            content: writableContent,
            change_reason: changeReason.trim(),
          },
        );
      workingDraft = updatedDraft;
    }
    setDraft(workingDraft);
    setContent(cloneClassificationStandardContent(workingDraft.content));
    return workingDraft;
  }

  const saveDraft = async () => {
    setBusy("save");
    try {
      const saved = await persistDraft();
      const checked =
        await classificationStandardApi.validateClassificationStandardDraft(
          saved.id,
          saved.revision,
        );
      setDraft(checked);
      await loadStandards();
      await loadValidation(saved.id);
      if (mode === "new") {
        navigateHash(
          "classification-standards",
          { standard: saved.standard_id, view: "edit" },
          { replace: true },
        );
      }
      notify("修改已保存");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  const prepareExcelDraft = async () => {
    if (dirty && (draft || content.labels.length))
      throw new Error("请先保存当前修改，再导入标签框架");
    if (draft) return draft;
    let created;
    if (mode === "new") {
      const category = content.variants[0];
      if (
        !content.name.trim() ||
        !content.product_context.trim() ||
        !category?.category_a.trim() ||
        !category?.category_b.trim()
      )
        throw new Error("请先填写标准名称、适用商品说明和适用品类");
      created = await classificationStandardApi.createClassificationStandard({
        name: content.name.trim(),
        product_context: content.product_context.trim(),
        category_a: category.category_a.trim(),
        category_b: category.category_b.trim(),
      });
    } else {
      created = await classificationStandardApi.createClassificationStandardDraft(
        requireDetail().id,
      );
    }
    setDraft(created);
    setContent(cloneClassificationStandardContent(created.content));
    setChangeReason("导入层级标签框架");
    return created;
  };

  const publish = async () => {
    setBusy("publish");
    try {
      const saved = await persistDraft();
      if (saved.validation.blocking.length > 0) {
        throw new Error(saved.validation.blocking.join("；"));
      }
      const standard =
        await classificationStandardApi.publishClassificationStandardDraft(saved.id, {
          expected_revision: saved.revision,
          reason: changeReason.trim() || "更新分类标准",
        });
      await loadStandards();
      await loadSelected(standard.id);
      navigateHash("classification-standards", { standard: standard.id });
      notify(saved.is_new ? "分类标准已创建并启用" : "分类标准已更新并启用");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  const importJson = async (
    /** @type {import("react").ChangeEvent<HTMLInputElement>} */ event,
  ) => {
    const file = event.target.files?.[0];
    if (!file || !detail) return;
    setBusy("import");
    try {
      const document = JSON.parse(await file.text());
      const workingDraft =
        draft ??
        (await classificationStandardApi.createClassificationStandardDraft(detail.id));
      const imported =
        await classificationStandardApi.importClassificationStandardDraft(
          workingDraft.id,
          {
            expected_revision: workingDraft.revision,
            document,
            change_reason: `导入 ${file.name}`,
          },
        );
      setDraft(imported);
      setContent(cloneClassificationStandardContent(imported.content));
      setChangeReason(imported.change_reason || `导入 ${file.name}`);
      await loadStandards();
      await loadValidation(imported.id);
      notify("JSON 已导入草稿，请检查后再发布");
    } catch (error) {
      notify(
        error instanceof SyntaxError ? "JSON 文件格式错误" : errorMessage(error),
        "error",
      );
    } finally {
      event.target.value = "";
      setBusy("");
    }
  };

  const changeContent = (
    /** @type {ClassificationStandardContent} */ value,
    /** @type {string | undefined} */ field,
  ) => {
    setContent(value);
    setFieldErrors((current) =>
      clearClassificationStandardContentFieldError(current, field),
    );
  };

  const applyExcel = (
    /** @type {ClassificationStandardContent} */ value,
    /** @type {string} */ filename,
  ) => {
    setContent(value);
    setChangeReason(`导入 ${filename}`);
    setFieldErrors({});
    notify("已采用层级预览，请检查层级和评价方向，保存后可运行样本验证");
  };

  return {
    detail,
    versions,
    draft,
    content,
    savedContent,
    changeReason,
    pageLoading,
    dirty,
    fieldErrors,
    validationAttempt,
    validationSources,
    validationRuns,
    selectedValidation,
    validationSourceId,
    validationSampleSize,
    setValidationSourceId,
    setValidationSampleSize,
    startSampleValidation,
    approveSampleValidation,
    selectValidation,
    setChangeReason,
    loadSelected,
    saveDraft,
    prepareExcelDraft,
    publish,
    importJson,
    changeContent,
    applyExcel,
  };
}
