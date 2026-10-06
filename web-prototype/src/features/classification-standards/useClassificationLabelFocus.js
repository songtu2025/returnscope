import { useEffect, useRef } from "react";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableContent} ClassificationStandardEditableContent */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardEditableLabel} ClassificationStandardEditableLabel */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardContent").ClassificationStandardFieldErrors} ClassificationStandardFieldErrors */
/** @typedef {number | string} LabelSelection */
/** @typedef {{type: "replace" | "retire"}} PendingLabelAction */
/** @typedef {{attempt?: number, index: number, field: string}} PendingLabelFocus */
/** @typedef {{label: ClassificationStandardEditableLabel, index: number, before?: ClassificationStandardEditableLabel, status: "新增" | "未修改" | "已修改" | "拟停用"}} ClassificationLabelChange */
/** @typedef {{content: ClassificationStandardEditableContent, baseContent: ClassificationStandardEditableContent | null, savedContent: ClassificationStandardEditableContent | null, onChange: (content: ClassificationStandardEditableContent, field?: string) => void, focusLabelCode?: string, fixRequest: ClassificationStandardValidationIssue | null, busy: boolean, initiallyEditing: boolean, fieldErrors: Partial<ClassificationStandardFieldErrors>, validationAttempt: number, section: string}} ClassificationLabelWorkbenchControllerOptions */

/** @typedef {Pick<ClassificationLabelWorkbenchControllerOptions,"content"|"fixRequest"|"busy"|"fieldErrors"|"validationAttempt"|"section"> & {selected: LabelSelection, query: string, group: string, editing: boolean, setSelected: import("react").Dispatch<import("react").SetStateAction<LabelSelection>>, setEditing: (value: boolean) => void, setQuery: (value: string) => void, setGroup: (value: string) => void}} LabelFocusOptions */
/** @typedef {{selectedRef: import("react").RefObject<HTMLButtonElement | null>, addLabelRef: import("react").RefObject<HTMLButtonElement | null>, emptyLabelRef: import("react").RefObject<HTMLButtonElement | null>, labelFieldRefs: import("react").RefObject<Map<string, HTMLElement | null>>, pendingFocusRef: import("react").RefObject<PendingLabelFocus | null>, handledFixRef: import("react").RefObject<ClassificationStandardValidationIssue | null>, focusedAttemptRef: import("react").RefObject<number | undefined>}} LabelFocusRefs */
/** @param {Partial<ClassificationStandardFieldErrors>} fieldErrors */
function firstLabelError(fieldErrors) {
  const index =
    fieldErrors.labels?.findIndex((item) => item.name || item.group || item.code) ?? -1;
  if (index < 0) return null;
  const errors = fieldErrors.labels?.[index];
  if (!errors) return null;
  /** @type {("name" | "group" | "code")[]} */
  const validatedFields = ["name", "group", "code"];
  const field = validatedFields.find((key) => errors[key]);
  if (!field) return null;
  return { index, field };
}
/** @param {Pick<LabelFocusRefs,"emptyLabelRef"|"addLabelRef"|"focusedAttemptRef">} refs @param {number} validationAttempt */
function focusEmptyLabel(
  { emptyLabelRef, addLabelRef, focusedAttemptRef },
  validationAttempt,
) {
  const target = emptyLabelRef.current || addLabelRef.current;
  if (target) {
    focusedAttemptRef.current = validationAttempt;
    target.focus();
  }
}
/** @param {HTMLButtonElement | null} target */
function centerLabelSelection(target) {
  const scrollContainer = target?.parentElement;
  if (!target || !scrollContainer) return;
  scrollContainer.scrollTop =
    target.offsetTop - scrollContainer.clientHeight / 2 + target.offsetHeight / 2;
}
/** @param {LabelFocusOptions} options @param {LabelFocusRefs} refs */
function useSelectedLabelScroll({ selected, query, group }, { selectedRef }) {
  useEffect(() => {
    const target = selectedRef.current;
    centerLabelSelection(target);
  }, [selected, query, group, selectedRef]);
}
/** @param {LabelFocusOptions} options @param {LabelFocusRefs} refs */
function useValidationFocus(
  { validationAttempt, busy, section, fieldErrors, setSelected, setEditing },
  refs,
) {
  const { focusedAttemptRef, pendingFocusRef, emptyLabelRef, addLabelRef } = refs;
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
      focusEmptyLabel(
        { emptyLabelRef, addLabelRef, focusedAttemptRef },
        validationAttempt,
      );
      return;
    }
    const issue = firstLabelError(fieldErrors);
    if (!issue) return;
    const { index, field } = issue;
    pendingFocusRef.current = { attempt: validationAttempt, index, field };
    setSelected(index);
    setEditing(true);
  }, [
    busy,
    fieldErrors,
    section,
    validationAttempt,
    focusedAttemptRef,
    pendingFocusRef,
    emptyLabelRef,
    addLabelRef,
    setSelected,
    setEditing,
  ]);
}
/** @param {LabelFocusOptions} options @param {LabelFocusRefs} refs */
function useFixRequestFocus(
  { fixRequest, section, content, setQuery, setGroup, setSelected, setEditing },
  { handledFixRef, pendingFocusRef },
) {
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
  }, [
    content.labels,
    fixRequest,
    section,
    handledFixRef,
    pendingFocusRef,
    setQuery,
    setGroup,
    setSelected,
    setEditing,
  ]);
}
/** @param {LabelFocusOptions} options @param {LabelFocusRefs} refs */
function usePendingLabelFocus(
  { busy, editing, section, selected, fixRequest },
  { pendingFocusRef, labelFieldRefs, focusedAttemptRef },
) {
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
  }, [
    busy,
    editing,
    section,
    selected,
    fixRequest,
    pendingFocusRef,
    labelFieldRefs,
    focusedAttemptRef,
  ]);
}
/** @param {LabelFocusOptions} options */
export function useClassificationLabelFocus(options) {
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

  const refs = {
    selectedRef,
    addLabelRef,
    emptyLabelRef,
    labelFieldRefs,
    pendingFocusRef,
    handledFixRef,
    focusedAttemptRef,
  };
  useSelectedLabelScroll(options, refs);
  useValidationFocus(options, refs);
  useFixRequestFocus(options, refs);
  usePendingLabelFocus(options, refs);
  return { selectedRef, addLabelRef, emptyLabelRef, labelFieldRefs };
}
