import { useCallback, useEffect, useRef, useState } from "react";
import {
  loadSelectedStandardDraft,
  classificationDraftErrorMessage as errorMessage,
} from "./classificationDraftSelection";
import {
  persistStandardDraft,
  prepareStandardExcelDraft,
} from "./classificationDraftPersistence";
import { importStandardDraftJson } from "./classificationDraftImport";

import { navigateHash } from "../../app/hashRouter";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  clearClassificationStandardContentFieldError,
  cloneClassificationStandardContent,
  contentFromClassificationStandardSnapshot,
  EMPTY_CLASSIFICATION_STANDARD_CONTENT,
} from "./classificationStandardContent";
import { useClassificationStandardValidationController } from "./useClassificationStandardValidationController";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */

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
    (/** @type {string} */ standardId) =>
      loadSelectedStandardDraft(standardId, {
        loadGenerationRef,
        state: {
          setPageLoading,
          setPageError,
          setDetail,
          setVersions,
          setDraft,
          setContent,
          setFieldErrors,
          setChangeReason,
        },
        loadValidation,
        clearValidation,
        errorMessage,
      }),
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
    return await persistStandardDraft({
      content,
      draft,
      mode,
      changeReason,
      requireDetail,
      state: { setFieldErrors, setValidationAttempt, setDraft, setContent },
    });
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

  const prepareExcelDraft = async () =>
    prepareStandardExcelDraft({
      dirty,
      draft,
      content,
      mode,
      requireDetail,
      state: { setDraft, setContent, setChangeReason },
    });

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
  ) =>
    importStandardDraftJson(event, {
      detail,
      draft,
      content,
      state: { setDraft, setContent, setChangeReason },
      setBusy,
      loadStandards,
      loadValidation,
      notify,
      errorMessage,
    });

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
