import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";
import { useEffect, useRef, useState } from "react";

import { taxonomyPath } from "../../lib/taxonomyPresentation";
import { labelChanges, reconcileLabelRules, sameLabel } from "./labelDraftPolicy";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {number | string} LabelSelection */
/** @typedef {{type: "replace" | "retire"}} PendingLabelAction */
/** @typedef {{attempt?: number, index: number, field: string}} PendingLabelFocus */
/** @typedef {{label: ClassificationStandardEditableLabel, index: number, before?: ClassificationStandardEditableLabel, status: "新增" | "未修改" | "已修改" | "拟停用"}} ClassificationLabelChange */
/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, savedContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, busy: string, initiallyEditing: boolean, fieldErrors: Partial<ClassificationStandardFieldErrors>, validationAttempt: number, section: string}} ClassificationLabelWorkbenchControllerOptions */

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
  const selectedRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const addLabelRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const emptyLabelRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const labelFieldRefs = useRef(
    /** @type {Map<string, HTMLElement | null>} */ (new Map()),
  );
  const pendingFocusRef = useRef(/** @type {PendingLabelFocus | null} */ (null));
  const handledFixRef = useRef(
    /** @type {ClassificationStandardValidationIssue | null} */ (null),
  );
  const focusedAttemptRef = useRef(/** @type {number | undefined} */ (0));

  useEffect(() => {
    const target = selectedRef.current;
    const scrollContainer = target?.parentElement;
    if (!target || !scrollContainer) return;
    scrollContainer.scrollTop =
      target.offsetTop - scrollContainer.clientHeight / 2 + target.offsetHeight / 2;
  }, [selected, query, group]);

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
  const conflictCodes = new Set(
    (content.validation_rules?.conflicting_label_sets ?? [])
      .filter((codes) => Boolean(label && codes.includes(label.code)))
      .flat(),
  );
  const labelDirty = Boolean(label && (removed ? saved : !sameLabel(label, saved)));
  const relatedLabels = content.labels.filter(
    (item) => item.code !== label?.code && conflictCodes.has(item.code),
  );

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

  useEffect(() => {
    if (
      !validationAttempt ||
      busy ||
      section !== "labels" ||
      focusedAttemptRef.current === validationAttempt
    ) {
      return;
    }
    if (fieldErrors.labels_empty) {
      const target = emptyLabelRef.current || addLabelRef.current;
      if (target) {
        focusedAttemptRef.current = validationAttempt;
        target.focus();
      }
      return;
    }
    const index =
      fieldErrors.labels?.findIndex((item) => item.name || item.group || item.code) ??
      -1;
    if (index < 0) return;
    const errors = fieldErrors.labels?.[index];
    if (!errors) return;
    /** @type {("name" | "group" | "code")[]} */
    const validatedFields = ["name", "group", "code"];
    const field = validatedFields.find((key) => errors[key]);
    if (!field) return;
    pendingFocusRef.current = { attempt: validationAttempt, index, field };
    setSelected(index);
    setEditing(true);
  }, [busy, fieldErrors, section, validationAttempt]);

  useEffect(() => {
    if (!fixRequest || section !== "labels" || handledFixRef.current === fixRequest) {
      return;
    }
    const index = fixRequest.label_code
      ? content.labels.findIndex((item) => item.code === fixRequest.label_code)
      : (fixRequest.label_index ?? -1);
    if (index < 0 || !content.labels[index]) return;
    handledFixRef.current = fixRequest;
    pendingFocusRef.current = {
      index,
      field: fixRequest.field || "description",
    };
    setQuery("");
    setGroup("");
    setSelected(index);
    setEditing(true);
  }, [content.labels, fixRequest, section]);

  useEffect(() => {
    const pendingFocus = pendingFocusRef.current;
    if (
      !pendingFocus ||
      busy ||
      !editing ||
      section !== "labels" ||
      selected !== pendingFocus.index
    ) {
      return;
    }
    const target = labelFieldRefs.current.get(
      `${pendingFocus.index}.${pendingFocus.field}`,
    );
    if (!target) return;
    target.focus();
    focusedAttemptRef.current = pendingFocus.attempt;
    pendingFocusRef.current = null;
  }, [busy, editing, section, selected, fixRequest]);

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
