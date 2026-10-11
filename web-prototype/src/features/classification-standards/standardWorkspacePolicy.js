import { contentFromClassificationStandardSnapshot } from "./classificationStandardContent";
import { labelChanges } from "./labelDraftPolicy";

/** @typedef {import("./classificationStandardWorkspaceContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("./classificationStandardWorkspaceContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("./classificationStandardWorkspaceContracts").ClassificationStandardWorkspaceProps} StandardWorkspaceProps */

/** @param {Pick<StandardWorkspaceProps,"isNew"|"detail"|"draft"|"content">} props */
export function standardChanges({ isNew, detail, draft, content }) {
  const editable = isNew || detail?.status === "active" || Boolean(draft);
  const baseContent = draft?.base_snapshot
    ? contentFromClassificationStandardSnapshot(draft.base_snapshot)
    : detail?.snapshot
      ? contentFromClassificationStandardSnapshot(detail.snapshot)
      : null;
  const changes = labelChanges(content.labels, baseContent?.labels).filter(
    (entry) => entry.status !== "未修改",
  );
  const contentKeys = /** @type {(keyof ClassificationStandardEditableContent)[]} */ (
    Object.keys(content)
  );
  const settingsChanges = contentKeys.filter(
    (key) =>
      key !== "labels" &&
      JSON.stringify(content[key]) !== JSON.stringify(baseContent?.[key]),
  ).length;
  const changeCount = changes.length + settingsChanges;
  return { editable, baseContent, changes, changeCount };
}
/** @param {ClassificationStandardValidationRunDetail | null} selectedValidation @param {boolean} dirty */
export function standardValidationEvidence(selectedValidation, dirty) {
  const validationEvidence =
    !dirty &&
    selectedValidation?.is_current &&
    selectedValidation.status === "completed" &&
    Number(selectedValidation.error_count) === 0 &&
    (selectedValidation.source?.comparison_type ?? "standard_version") ===
      "standard_version"
      ? selectedValidation
      : null;
  return validationEvidence;
}
/** @param {Pick<StandardWorkspaceProps,"busy"|"draft"|"dirty"|"isNew">} props */
export function standardPublicationState({ busy, draft, dirty, isNew }) {
  const structureBlocked = !dirty && Boolean(draft?.validation.blocking.length);
  const publishDisabled =
    Boolean(busy) || (!isNew && !draft && !dirty) || structureBlocked;
  return {
    publishDisabled,
    publishLabel: structureBlocked ? "请先修复结构问题" : "保存并启用",
  };
}
