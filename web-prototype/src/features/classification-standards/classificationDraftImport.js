import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { cloneClassificationStandardContent } from "./classificationStandardContent";
import { createWorkingDraft } from "./classificationDraftPersistence";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */

/** @param {File} file @param {ClassificationStandardDraft | null} draft @param {ClassificationStandardDetail} detail @param {ClassificationStandardEditableContent} content */
async function readAndImportDraft(file, draft, detail, content) {
  const document = JSON.parse(await file.text());
  const workingDraft =
    draft ?? (await createWorkingDraft("edit", content, () => detail));
  const imported = await classificationStandardApi.importClassificationStandardDraft(
    workingDraft.id,
    {
      expected_revision: workingDraft.revision,
      document,
      change_reason: `导入 ${file.name}`,
    },
  );
  return imported;
}
/** @param {import("react").ChangeEvent<HTMLInputElement>} event @param {{detail: ClassificationStandardDetail | null, draft: ClassificationStandardDraft | null, content: ClassificationStandardEditableContent, state: {setDraft: (value: ClassificationStandardDraft) => void, setContent: (value: ClassificationStandardEditableContent) => void, setChangeReason: (value: string) => void}, setBusy: (value: string) => void, loadStandards: () => Promise<unknown[]>, loadValidation: (id: string) => Promise<void>, notify: (message: string, tone?: string) => void, errorMessage: (error: unknown) => string}} options */
export async function importStandardDraftJson(
  event,
  {
    detail,
    draft,
    content,
    state,
    setBusy,
    loadStandards,
    loadValidation,
    notify,
    errorMessage,
  },
) {
  const file = event.target.files?.[0];
  if (!file || !detail) return;
  setBusy("import");
  try {
    const imported = await readAndImportDraft(file, draft, detail, content);
    state.setDraft(imported);
    state.setContent(cloneClassificationStandardContent(imported.content));
    state.setChangeReason(imported.change_reason || `导入 ${file.name}`);
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
}
