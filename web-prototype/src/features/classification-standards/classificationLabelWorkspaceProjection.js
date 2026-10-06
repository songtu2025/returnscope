import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";
import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { labelChanges, sameLabel } from "./labelDraftPolicy";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {number | string} LabelSelection */
/** @typedef {{type: "replace" | "retire"}} PendingLabelAction */
/** @typedef {{attempt?: number, index: number, field: string}} PendingLabelFocus */
/** @typedef {{label: ClassificationStandardEditableLabel, index: number, before?: ClassificationStandardEditableLabel, status: "新增" | "未修改" | "已修改" | "拟停用"}} ClassificationLabelChange */
/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, savedContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, busy: boolean, initiallyEditing: boolean, fieldErrors: Partial<ClassificationStandardFieldErrors>, validationAttempt: number, section: string}} ClassificationLabelWorkbenchControllerOptions */

/** @typedef {Pick<ClassificationLabelWorkbenchControllerOptions,"content"|"baseContent"|"savedContent"> & {selected: LabelSelection, query: string, group: string, origins: Record<string,string | null>}} ProjectionOptions */
/** @param {ProjectionOptions} options */
function selectedLabel({ content, baseContent, savedContent, selected, origins }) {
  /** @type {ClassificationLabelChange[]} */
  const entries = labelChanges(content.labels, baseContent?.labels);
  const entry =
    typeof selected === "number"
      ? entries.find((item) => item.index === selected)
      : entries.find((item) => item.index < 0 && item.label.code === selected);
  const label = entry?.label;
  const published =
    Boolean(entry?.before) && Boolean(label && !(label.code in origins));
  const removed = entry?.status === "拟停用";
  const originalCode = label ? origins[label.code] : null;
  const saved = label
    ? (savedContent?.labels.find((item) => item.code === label.code) ??
      savedContent?.labels.find((item) => item.code === originalCode))
    : undefined;
  return { entries, entry, label, published, removed, saved };
}
/** @param {ClassificationStandardEditableContent} content @param {ClassificationLabelChange[]} entries */
function labelGroups(content, entries) {
  const groups = [...new Set(entries.map((item) => item.label.group).filter(Boolean))];
  const hierarchical = content.structure_version === 2;
  const configuredGroups = content.validation_rules?.allowed_groups;
  const allowedGroups = hierarchical
    ? (content.categories ?? [])
        .filter((item) => !item.parent_code)
        .map((item) => item.name)
    : configuredGroups?.length
      ? configuredGroups
      : BUSINESS_GROUPS;
  return { groups, hierarchical, allowedGroups };
}
/** @param {ClassificationStandardEditableContent} content @param {ClassificationLabelChange[]} entries @param {string} query @param {string} group */
function matchingLabels(content, entries, query, group) {
  const normalizedQuery = query.trim().toLowerCase();
  const matches = entries.filter(
    ({ label: item }) =>
      (!group || item.group === group) &&
      [
        item.name,
        item.code,
        item.description,
        ...taxonomyPath(content, item),
        ...item.keywords,
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery),
  );
  return matches;
}
/** @param {ClassificationStandardEditableContent} content @param {ClassificationStandardEditableLabel | undefined} label */
function relatedLabelRules(content, label) {
  const conflictCodes = new Set(
    (content.validation_rules?.conflicting_label_sets ?? [])
      .filter((codes) => Boolean(label && codes.includes(label.code)))
      .flat(),
  );
  const relatedLabels = content.labels.filter(
    (item) => item.code !== label?.code && conflictCodes.has(item.code),
  );

  return relatedLabels;
}
/** @param {ProjectionOptions} options */
export function classificationLabelWorkspaceProjection(options) {
  const { entries, entry, label, published, removed, saved } = selectedLabel(options);
  const { content, query, group } = options;
  return {
    entry,
    label,
    published,
    removed,
    saved,
    labelDirty: Boolean(label && (removed ? saved : !sameLabel(label, saved))),
    ...labelGroups(content, entries),
    matches: matchingLabels(content, entries, query, group),
    relatedLabels: relatedLabelRules(content, label),
    entries,
  };
}
