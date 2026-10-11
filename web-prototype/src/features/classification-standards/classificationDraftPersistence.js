import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  validateClassificationStandardContent,
  classificationStandardContentFieldErrors,
  writableClassificationStandardContent,
  cloneClassificationStandardContent,
} from "./classificationStandardContent";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */

/** @param {string} mode @param {ClassificationStandardEditableContent} content @param {() => ClassificationStandardDetail} requireDetail @returns {Promise<ClassificationStandardDraft>} */
export async function createWorkingDraft(mode, content, requireDetail) {
  if (mode === "new") {
    const firstCategory = content.variants[0];
    const createdDraft = await classificationStandardApi.createClassificationStandard({
      name: content.name.trim(),
      product_context: content.product_context.trim(),
      category_a: firstCategory.category_a.trim(),
      category_b: firstCategory.category_b.trim(),
    });
    return createdDraft;
  }
  return await classificationStandardApi.createClassificationStandardDraft(
    requireDetail().id,
  );
}
/** @typedef {{setFieldErrors: (value: Partial<ClassificationStandardFieldErrors>) => void, setValidationAttempt: import("react").Dispatch<import("react").SetStateAction<number>>, setDraft: (value: ClassificationStandardDraft) => void, setContent: (value: ClassificationStandardEditableContent) => void}} PersistDraftState */
/** @param {{content: ClassificationStandardEditableContent, draft: ClassificationStandardDraft | null, mode: string, changeReason: string, requireDetail: () => ClassificationStandardDetail, state: PersistDraftState}} options @returns {Promise<ClassificationStandardDraft>} */
export async function persistStandardDraft({
  content,
  draft,
  mode,
  changeReason,
  requireDetail,
  state,
}) {
  const error = validateClassificationStandardContent(content);
  if (error) {
    state.setFieldErrors(classificationStandardContentFieldErrors(content));
    state.setValidationAttempt((value) => value + 1);
    throw new Error(error);
  }
  const writableContent = writableClassificationStandardContent(content);
  state.setFieldErrors({});

  let workingDraft = draft;
  if (!workingDraft)
    workingDraft = await createWorkingDraft(mode, content, requireDetail);

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
  state.setDraft(workingDraft);
  state.setContent(cloneClassificationStandardContent(workingDraft.content));
  return workingDraft;
}

/** @param {ClassificationStandardDraft} saved @param {string} reason @param {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail | null} selectedValidation @param {string | null} validationRunId */
export async function enableStandardDraft(
  saved,
  reason,
  selectedValidation,
  validationRunId,
) {
  if (saved.validation.blocking.length > 0) {
    throw new Error(saved.validation.blocking.join("；"));
  }
  return await classificationStandardApi.publishClassificationStandardDraft(saved.id, {
    expected_revision: saved.revision,
    reason: reason.trim() || "更新分类标准",
    // 编辑后的修订不能沿用旧内容的测试记录。
    validation_run_id:
      selectedValidation?.id === validationRunId &&
      selectedValidation.draft_revision === saved.revision &&
      selectedValidation.is_current
        ? validationRunId
        : null,
  });
}

/** @param {{dirty: boolean, draft: ClassificationStandardDraft | null, content: ClassificationStandardEditableContent, mode: string, requireDetail: () => ClassificationStandardDetail, state: {setDraft: (value: ClassificationStandardDraft) => void, setContent: (value: ClassificationStandardEditableContent) => void, setChangeReason: (value: string) => void}}} options @returns {Promise<ClassificationStandardDraft>} */
export async function prepareStandardExcelDraft({
  dirty,
  draft,
  content,
  mode,
  requireDetail,
  state,
}) {
  if (dirty && (draft || content.labels.length))
    throw new Error("请先保存当前修改，再导入标签框架");
  if (draft) return draft;
  if (mode === "new") {
    const category = content.variants[0];
    if (
      !content.name.trim() ||
      !content.product_context.trim() ||
      !category?.category_a.trim() ||
      !category?.category_b.trim()
    )
      throw new Error("请先填写标准名称、适用商品说明和适用品类");
  }
  const created = await createWorkingDraft(mode, content, requireDetail);
  state.setDraft(created);
  state.setContent(cloneClassificationStandardContent(created.content));
  state.setChangeReason("导入层级标签框架");
  return created;
}
