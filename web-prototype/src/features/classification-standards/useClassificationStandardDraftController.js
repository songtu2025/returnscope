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
  writableClassificationStandardContent,
} from "./classificationStandardContent";
import { useClassificationStandardValidationController } from "./useClassificationStandardValidationController";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
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
    /** @type {ClassificationStandardEditableContent} */ (
      cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT)
    ),
  );
  const [changeReason, setChangeReason] = useState("");
  const [pageLoading, setPageLoading] = useState(false);
  const [pageError, setPageError] = useState(
    /** @type {{id: string, message: string} | null} */ (null),
  );
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
      setPageError(null);
      try {
        const [standard, versionRows] = await Promise.all([
          classificationStandardApi.classificationStandard(standardId),
          classificationStandardApi.classificationStandardVersions(standardId),
        ]);
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
        if (generation === loadGenerationRef.current) {
          setPageError({ id: standardId, message: errorMessage(error) });
          throw error;
        }
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
      setPageError(null);
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
      setPageError(null);
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
        const createdDraft =
          await classificationStandardApi.createClassificationStandard({
            name: content.name.trim(),
            product_context: content.product_context.trim(),
            category_a: firstCategory.category_a.trim(),
            category_b: firstCategory.category_b.trim(),
          });
        workingDraft = createdDraft;
      } else {
        const createdDraft =
          await classificationStandardApi.createClassificationStandardDraft(
            requireDetail().id,
          );
        workingDraft = createdDraft;
      }
    }

    if (JSON.stringify(writableContent) !== JSON.stringify(workingDraft.content)) {
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

  const publish = async (/** @type {string | null} */ validationRunId = null) => {
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
          validation_run_id: validationRunId,
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
    /** @type {ClassificationStandardEditableContent} */ value,
    /** @type {string | undefined} */ field,
  ) => {
    setContent(value);
    setFieldErrors((current) =>
      clearClassificationStandardContentFieldError(current, field),
    );
  };

  const applyExcel = (
    /** @type {ClassificationStandardEditableContent} */ value,
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
    pageError,
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
