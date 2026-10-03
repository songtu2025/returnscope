import {
  standardChanges,
  standardValidationEvidence,
  standardPublicationState,
} from "./standardWorkspacePolicy";
import { useEffect, useRef, useState } from "react";

/** @typedef {import("./classificationStandardWorkspaceContracts").ClassificationStandardValidationIssue} ClassificationStandardValidationIssue */
/** @typedef {import("./classificationStandardWorkspaceContracts").ClassificationStandardWorkspaceProps} ClassificationStandardWorkspaceProps */

/** @param {import("./classificationStandardWorkspaceContracts").ClassificationStandardWorkspaceProps} props */
export function useStandardWorkspace({
  isNew,
  detail,
  draft,
  content,
  changeReason,
  busy,
  dirty,
  selectedValidation,
  fieldErrors,
  validationAttempt,
}) {
  const [section, setSection] = useState(isNew ? "settings" : "labels");
  const [confirmBack, setConfirmBack] = useState(false);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [fixRequest, setFixRequest] = useState(
    /** @type {ClassificationStandardValidationIssue | null} */ (null),
  );
  /** @param {ClassificationStandardValidationIssue} issue */
  const fixIssue = (issue) => {
    setSection(
      issue.kind === "invalid_rule" ||
        (!issue.label_code &&
          issue.label_index == null &&
          issue.kind === "missing_field")
        ? "settings"
        : "labels",
    );
    setFixRequest({ ...issue });
  };
  const handledValidationAttempt = useRef(validationAttempt);
  const { editable, baseContent, changes, changeCount } = standardChanges({
    isNew,
    detail,
    draft,
    content,
  });
  const validationEvidence = standardValidationEvidence(selectedValidation);
  const { publishDisabled, publishLabel } = standardPublicationState({
    busy,
    draft,
    dirty,
    changeReason,
  });
  useEffect(() => {
    if (!validationAttempt || handledValidationAttempt.current === validationAttempt) {
      return;
    }
    handledValidationAttempt.current = validationAttempt;
    const hasSettingsError =
      fieldErrors.name ||
      fieldErrors.product_context ||
      fieldErrors.variants_empty ||
      fieldErrors.variants?.some((item) => item.category_a || item.category_b);
    setSection(hasSettingsError ? "settings" : "labels");
  }, [fieldErrors, validationAttempt]);

  return {
    section,
    setSection,
    confirmBack,
    setConfirmBack,
    confirmPublish,
    setConfirmPublish,
    fixRequest,
    fixIssue,
    editable,
    baseContent,
    changes,
    changeCount,
    validationEvidence,
    publishDisabled,
    publishLabel,
  };
}
