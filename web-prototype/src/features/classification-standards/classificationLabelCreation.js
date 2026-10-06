/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {number | string} LabelSelection */
/** @typedef {{type: "replace" | "retire"}} PendingLabelAction */
/** @typedef {{attempt?: number, index: number, field: string}} PendingLabelFocus */
/** @typedef {{label: ClassificationStandardEditableLabel, index: number, before?: ClassificationStandardEditableLabel, status: "新增" | "未修改" | "已修改" | "拟停用"}} ClassificationLabelChange */
/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, savedContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, busy: boolean, initiallyEditing: boolean, fieldErrors: Partial<ClassificationStandardFieldErrors>, validationAttempt: number, section: string}} ClassificationLabelWorkbenchControllerOptions */

/** @param {{entries: ClassificationLabelChange[], source?: ClassificationStandardEditableLabel, hierarchical: boolean, allowedGroups: string[], group: string, content: ClassificationStandardEditableContent}} options */
export function createWorkspaceLabel({
  entries,
  source,
  hierarchical,
  allowedGroups,
  group,
  content,
}) {
  const usedCodes = new Set(entries.map((item) => item.label.code));
  const prefix = source
    ? `${source.code}_V`
    : hierarchical
      ? `LABEL_${crypto.randomUUID().replaceAll("-", "").toUpperCase()}_`
      : "NEW_LABEL_";
  let suffix = source ? 2 : 1;
  while (usedCodes.has(`${prefix}${suffix}`)) suffix += 1;
  /** @type {ClassificationStandardEditableLabel} */
  const newLabel = source
    ? { ...source, code: `${prefix}${suffix}`, allowed_claim_ids: [] }
    : {
        code: `${prefix}${suffix}`,
        name: "",
        group: allowedGroups.includes(group) ? group : allowedGroups[0] || "",
        parent_code: hierarchical ? (content.categories?.[0]?.code ?? null) : null,
        description: "",
        keywords: [],
        exclusions: [],
        examples: [],
        allowed_sentiments: ["NEGATIVE"],
        allowed_claim_ids: [],
      };
  return newLabel;
}
