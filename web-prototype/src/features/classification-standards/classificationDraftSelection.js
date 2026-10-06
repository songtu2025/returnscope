import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  cloneClassificationStandardContent,
  contentFromClassificationStandardSnapshot,
} from "./classificationStandardContent";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft} ClassificationStandardDraft */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */

/** @typedef {{setDetail: (value: ClassificationStandardDetail) => void, setVersions: (value: ClassificationStandardVersion[]) => void, setDraft: (value: ClassificationStandardDraft | null) => void, setContent: (value: ClassificationStandardEditableContent) => void, setFieldErrors: (value: Partial<ClassificationStandardFieldErrors>) => void, setChangeReason: (value: string) => void, setPageLoading: (value: boolean) => void, setPageError: (value: {id: string, message: string} | null) => void}} SelectedDraftState */
/** @param {string} standardId */
async function readStandardDraft(standardId) {
  const [standard, versionRows] = await Promise.all([
    classificationStandardApi.classificationStandard(standardId),
    classificationStandardApi.classificationStandardVersions(standardId),
  ]);
  const draftValue = standard.draft_id
    ? await classificationStandardApi.classificationStandardDraft(standard.draft_id)
    : null;
  return { standard, versionRows, draftValue };
}
/** @param {string} standardId @param {{loadGenerationRef: import("react").RefObject<number>, state: SelectedDraftState, loadValidation: (id: string) => Promise<void>, clearValidation: () => void, errorMessage: (error: unknown) => string}} options */
export async function loadSelectedStandardDraft(
  standardId,
  { loadGenerationRef, state, loadValidation, clearValidation, errorMessage },
) {
  const generation = ++loadGenerationRef.current;
  state.setPageLoading(true);
  state.setPageError(null);
  try {
    const { standard, versionRows, draftValue } = await readStandardDraft(standardId);
    if (generation !== loadGenerationRef.current) return;
    state.setDetail(standard);
    state.setVersions(versionRows);
    state.setDraft(draftValue);
    state.setContent(
      cloneClassificationStandardContent(
        draftValue?.content ??
          contentFromClassificationStandardSnapshot(standard.snapshot),
      ),
    );
    state.setFieldErrors({});
    state.setChangeReason(draftValue?.change_reason || `更新${standard.name}`);
    if (draftValue) await loadValidation(draftValue.id);
    else clearValidation();
  } catch (error) {
    if (generation === loadGenerationRef.current) {
      state.setPageError({ id: standardId, message: errorMessage(error) });
      throw error;
    }
  } finally {
    if (generation === loadGenerationRef.current) state.setPageLoading(false);
  }
}

/** @param {unknown} error */
export function classificationDraftErrorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}
