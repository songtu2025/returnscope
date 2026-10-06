import { useState } from "react";
import { useClassificationLabelFocus } from "./useClassificationLabelFocus";
import { classificationLabelWorkspaceProjection } from "./classificationLabelWorkspaceProjection";
import { createWorkspaceLabel } from "./classificationLabelCreation";

import { reconcileLabelRules } from "./labelDraftPolicy";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {number | string} LabelSelection */
/** @typedef {{type: "replace" | "retire"}} PendingLabelAction */
/** @typedef {{attempt?: number, index: number, field: string}} PendingLabelFocus */
/** @typedef {{label: ClassificationStandardEditableLabel, index: number, before?: ClassificationStandardEditableLabel, status: "新增" | "未修改" | "已修改" | "拟停用"}} ClassificationLabelChange */
/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, savedContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, busy: boolean, initiallyEditing: boolean, fieldErrors: Partial<ClassificationStandardFieldErrors>, validationAttempt: number, section: string}} ClassificationLabelWorkbenchControllerOptions */

/** @param {ClassificationLabelWorkbenchControllerOptions} options */
export function useClassificationLabelWorkbenchController({
  content,
  baseContent,
  savedContent,
  onChange,
  focusLabelCode,
  fixRequest,
  busy,
  initiallyEditing,
  fieldErrors,
  validationAttempt,
  section,
}) {
  const [selected, setSelected] = useState(
    () =>
      /** @type {LabelSelection} */ (
        Math.max(
          0,
          content.labels.findIndex((label) => label.code === focusLabelCode),
        )
      ),
  );
  const [editing, setEditing] = useState(initiallyEditing);
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("");
  const [pending, setPending] = useState(
    /** @type {PendingLabelAction | null} */ (null),
  );
  const [keywordText, setKeywordText] = useState("");
  const [origins, setOrigins] = useState(
    () => /** @type {Record<string, string | null>} */ ({}),
  );
  const { selectedRef, addLabelRef, emptyLabelRef, labelFieldRefs } =
    useClassificationLabelFocus({
      content,
      fixRequest,
      busy,
      fieldErrors,
      validationAttempt,
      section,
      selected,
      query,
      group,
      editing,
      setSelected,
      setEditing,
      setQuery,
      setGroup,
    });
  const {
    entries,
    entry,
    label,
    published,
    removed,
    saved,
    groups,
    hierarchical,
    allowedGroups,
    matches,
    labelDirty,
    relatedLabels,
  } = classificationLabelWorkspaceProjection({
    content,
    baseContent,
    savedContent,
    selected,
    origins,
    query,
    group,
  });

  /** @param {Partial<ClassificationStandardEditableLabel>} updates */
  const updateLabel = (updates) => {
    if (!entry || !label) return;
    const field = Object.keys(updates)[0] ?? "";
    const nextCode = updates.code;
    if (nextCode !== undefined && nextCode !== label.code) {
      setOrigins((current) => {
        const next = {
          ...current,
          [nextCode]: current[label.code] ?? label.code,
        };
        delete next[label.code];
        return next;
      });
    }
    onChange(
      {
        ...content,
        labels: content.labels.map((item, index) =>
          index === entry.index ? { ...item, ...updates } : item,
        ),
      },
      `labels.${entry.index}.${field}`,
    );
  };

  /** @param {ClassificationStandardEditableLabel[]} labels @param {string} [restoredCode] @param {string} [field] */
  const changeLabels = (labels, restoredCode, field) =>
    onChange(
      {
        ...content,
        labels,
        validation_rules: hierarchical
          ? content.validation_rules
          : reconcileLabelRules(
              content.validation_rules,
              labels,
              baseContent?.validation_rules,
              restoredCode,
            ),
      },
      field,
    );

  /** @param {LabelSelection} value */
  const selectLabel = (value) => {
    setSelected(value);
    setKeywordText("");
  };

  /** @param {ClassificationStandardEditableLabel | undefined} [source] */
  const addLabel = (source) => {
    if (source && !entry) return;
    setEditing(true);
    const newLabel = createWorkspaceLabel({
      entries,
      source,
      hierarchical,
      allowedGroups,
      group,
      content,
    });
    const labels = source
      ? content.labels.map((item, index) => (index === entry?.index ? newLabel : item))
      : [...content.labels, newLabel];
    setOrigins((current) => ({
      ...current,
      [newLabel.code]: source?.code ?? null,
    }));
    changeLabels(labels, undefined, "labels_empty");
    selectLabel(source && entry ? entry.index : labels.length - 1);
    setQuery("");
    setGroup("");
    setPending(null);
  };

  /** @param {string} text */
  const commitKeywords = (text) => {
    if (!label) return;
    const values = text
      .split(/[,，;；\n]+/)
      .map((word) => word.trim())
      .filter(Boolean);
    if (values.length) {
      updateLabel({
        keywords: [...new Set([...(label.keywords ?? []), ...values])],
      });
    }
    setKeywordText("");
  };

  const retireLabel = () => {
    if (!entry || !label) return;
    const labels = content.labels.filter((_item, index) => index !== entry.index);
    changeLabels(labels);
    selectLabel(published ? label.code : Math.max(0, entry.index - 1));
    setPending(null);
  };

  const restoreLabel = () => {
    if (!label) return;
    changeLabels([...content.labels, label], label.code);
    selectLabel(content.labels.length);
  };

  const undoLabel = () => {
    if (!entry || !label) return;
    setOrigins((current) => {
      const next = { ...current };
      delete next[label.code];
      if (saved) delete next[saved.code];
      return next;
    });
    if (removed && saved) {
      changeLabels([...content.labels, saved], saved.code);
      selectLabel(content.labels.length);
    } else if (saved) {
      changeLabels(
        content.labels.map((item, index) => (index === entry.index ? saved : item)),
        saved.code,
      );
    } else {
      changeLabels(content.labels.filter((_item, index) => index !== entry.index));
      selectLabel(0);
    }
    setKeywordText("");
  };

  return {
    entry,
    label,
    published,
    removed,
    labelDirty,
    groups,
    hierarchical,
    allowedGroups,
    matches,
    relatedLabels,
    selected,
    editing,
    query,
    group,
    pending,
    keywordText,
    selectedRef,
    addLabelRef,
    emptyLabelRef,
    labelFieldRefs,
    setEditing,
    setQuery,
    setGroup,
    setPending,
    setKeywordText,
    updateLabel,
    selectLabel,
    addLabel,
    commitKeywords,
    retireLabel,
    restoreLabel,
    undoLabel,
  };
}
