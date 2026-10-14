import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { navigateHash } from "../../app/hashRouter";
import { classificationDraftErrorMessage } from "./classificationDraftSelection";

/** @param {{detail: import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail | null, draft: import("../../shared/api/classificationStandardContracts").ClassificationStandardDraft | null, setBusy: (value: string) => void, loadStandards: () => Promise<unknown>, loadSelected: (id: string) => Promise<unknown>, notify: (message: string, tone?: string) => void}} options */
export function useStandardLifecycle({
  detail,
  draft,
  setBusy,
  loadStandards,
  loadSelected,
  notify,
}) {
  /** @param {"enable" | "discard"} action */
  const run = async (action) => {
    if (!detail || (action === "discard" && !draft)) return;
    setBusy(action);
    try {
      if (action === "enable") {
        await classificationStandardApi.enableClassificationStandard(
          detail.id,
          detail.standard_version_id,
        );
      } else if (draft) {
        await classificationStandardApi.discardClassificationStandardDraft(draft.id, {
          expected_revision: draft.revision,
          reason: "用户放弃暂存修改",
        });
      }
      await loadStandards();
      if (action === "discard" && draft?.is_new)
        navigateHash("classification-standards");
      else await loadSelected(detail.id);
      notify(action === "enable" ? "分类标准已重新启用" : "暂存修改已放弃");
    } catch (error) {
      notify(classificationDraftErrorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };
  return { enable: () => run("enable"), discard: () => run("discard") };
}
