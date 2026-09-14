import { useCallback, useEffect, useState } from "react";

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
  const [detail, setDetail] = useState(null);
  const [versions, setVersions] = useState([]);
  const [draft, setDraft] = useState(null);
  const [content, setContent] = useState(
    cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT),
  );
  const [changeReason, setChangeReason] = useState("");
  const [pageLoading, setPageLoading] = useState(false);
  const [fieldErrors, setFieldErrors] = useState({});
  const [validationAttempt, setValidationAttempt] = useState(0);

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

  const loadSelected = useCallback(
    async (standardId) => {
      setPageLoading(true);
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
      } finally {
        setPageLoading(false);
      }
    },
    [clearValidation, loadValidation],
  );

  useEffect(() => {
    if (mode === "new") {
      setDetail(null);
      setVersions([]);
      setDraft(null);
      setContent(
        cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT),
      );
      setFieldErrors({});
      setChangeReason("新增分类标准");
      return;
    }
    if (!selectedId) return;
    loadSelected(selectedId).catch((error) => notify(error.message, "error"));
  }, [loadSelected, mode, notify, selectedId]);

  const savedContent =
    draft?.content ??
    (detail?.snapshot
      ? contentFromClassificationStandardSnapshot(detail.snapshot)
      : EMPTY_CLASSIFICATION_STANDARD_CONTENT);
  const dirty = JSON.stringify(content) !== JSON.stringify(savedContent);

  useEffect(() => {
    if (!dirty || !["edit", "new"].includes(mode)) return;
    const warnBeforeClose = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeClose);
    return () => window.removeEventListener("beforeunload", warnBeforeClose);
  }, [dirty, mode]);

  async function persistDraft() {
    const error = validateClassificationStandardContent(content);
    if (error) {
      setFieldErrors(classificationStandardContentFieldErrors(content));
      setValidationAttempt((value) => value + 1);
      throw new Error(error);
    }
    setFieldErrors({});

    let workingDraft = draft;
    if (!workingDraft) {
      if (mode === "new") {
        const firstCategory = content.variants[0];
        workingDraft = await classificationStandardApi.createClassificationStandard({
          name: content.name.trim(),
          product_context: content.product_context.trim(),
          category_a: firstCategory.category_a.trim(),
          category_b: firstCategory.category_b.trim(),
        });
      } else {
        workingDraft =
          await classificationStandardApi.createClassificationStandardDraft(detail.id);
      }
    }

    if (JSON.stringify(content) !== JSON.stringify(workingDraft.content)) {
      workingDraft = await classificationStandardApi.updateClassificationStandardDraft(
        workingDraft.id,
        {
          expected_revision: workingDraft.revision,
          content,
          change_reason: changeReason.trim(),
        },
      );
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
      notify(error.message, "error");
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
        detail.id,
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
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const importJson = async (event) => {
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
        error instanceof SyntaxError ? "JSON 文件格式错误" : error.message,
        "error",
      );
    } finally {
      event.target.value = "";
      setBusy("");
    }
  };

  const changeContent = (value, field) => {
    setContent(value);
    setFieldErrors((current) =>
      clearClassificationStandardContentFieldError(current, field),
    );
  };

  const applyExcel = (value, filename) => {
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
