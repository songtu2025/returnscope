import { useCallback, useEffect, useRef, useState } from "react";

import { classificationStandardApi } from "../../shared/api/classificationStandardApi";

/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationComparisonType} ValidationComparisonType */
/** @typedef {import("../../shared/api/classificationStandardContracts").ValidationSampleSize} ValidationSampleSize */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunDetail} ClassificationStandardValidationRunDetail */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationRunSummary} ClassificationStandardValidationRunSummary */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardValidationSource} ClassificationStandardValidationSource */
/** @typedef {{id: string, revision: number}} ValidationDraft */

/**
 * @typedef {object} ValidationControllerOptions
 * @property {ValidationDraft | null} draft
 * @property {(message: string, tone?: string) => void} notify
 * @property {() => Promise<ValidationDraft>} persistDraft
 * @property {(value: string) => void} setBusy
 */

/**
 * @param {string} value
 * @returns {value is ValidationComparisonType}
 */
function isValidationComparisonType(value) {
  return ["standard_version", "keyword_ab", "semantic_ab"].includes(value);
}

/** @param {ValidationControllerOptions} options */
export function useClassificationStandardValidationController({
  draft,
  notify,
  persistDraft,
  setBusy,
}) {
  const [validationSources, setValidationSources] = useState(
    /** @type {ClassificationStandardValidationSource[]} */ ([]),
  );
  const [validationRuns, setValidationRuns] = useState(
    /** @type {ClassificationStandardValidationRunSummary[]} */ ([]),
  );
  const [selectedValidation, setSelectedValidation] = useState(
    /** @type {ClassificationStandardValidationRunDetail | null} */ (null),
  );
  const [validationSourceId, setValidationSourceId] = useState("");
  const [validationSampleSize, setValidationSampleSize] = useState(
    /** @type {ValidationSampleSize} */ (20),
  );
  const requestOwnershipRef = useRef({
    foreground: 0,
    background: 0,
    loading: false,
    draftId: /** @type {string | null} */ (null),
    runId: /** @type {string | null} */ (null),
  });

  const loadValidation = useCallback(
    async (
      /** @type {string} */ draftId,
      /** @type {string | null} */ preferredRunId = null,
      /** @type {boolean} */ background = false,
    ) => {
      const ownership = requestOwnershipRef.current;
      let foregroundGeneration = ownership.foreground;
      let backgroundGeneration = ownership.background;
      if (background) {
        if (ownership.draftId !== draftId || ownership.loading) return;
        backgroundGeneration = ++ownership.background;
      } else {
        ownership.draftId = draftId;
        ownership.runId = preferredRunId;
        foregroundGeneration = ++ownership.foreground;
        ownership.background += 1;
        ownership.loading = true;
      }
      const isCurrent = () =>
        ownership.draftId === draftId &&
        ownership.foreground === foregroundGeneration &&
        (!background || ownership.background === backgroundGeneration);
      try {
        /** @type {[ClassificationStandardValidationSource[], ClassificationStandardValidationRunSummary[]]} */
        const [sources, runs] = await Promise.all([
          classificationStandardApi.classificationStandardValidationSources(draftId),
          classificationStandardApi.classificationStandardValidationRuns(draftId),
        ]);
        if (!isCurrent()) return;
        setValidationSources(sources);
        setValidationRuns(runs);
        setValidationSourceId((current) =>
          sources.some((source) => source.result_version_id === current)
            ? current
            : sources[0]?.result_version_id || "",
        );
        const selectedRunId = ownership.runId || runs[0]?.id || null;
        ownership.runId = selectedRunId;
        if (!selectedRunId) {
          setSelectedValidation(null);
          return;
        }
        const selected =
          await classificationStandardApi.classificationStandardValidationRun(
            selectedRunId,
          );
        if (isCurrent() && ownership.runId === selectedRunId) {
          setSelectedValidation(selected);
        }
      } finally {
        if (
          !background &&
          ownership.foreground === foregroundGeneration &&
          ownership.draftId === draftId
        ) {
          ownership.loading = false;
        }
      }
    },
    [],
  );

  const clearValidation = useCallback(() => {
    const ownership = requestOwnershipRef.current;
    ownership.loading = false;
    ownership.draftId = null;
    ownership.runId = null;
    setValidationSources([]);
    setValidationRuns([]);
    setSelectedValidation(null);
    setValidationSourceId("");
  }, []);

  useEffect(
    () => () => {
      requestOwnershipRef.current.draftId = null;
    },
    [],
  );

  useEffect(() => {
    const active = validationRuns.some((run) =>
      ["queued", "running"].includes(run.status),
    );
    if (!draft || !active) return undefined;
    const timer = window.setInterval(() => {
      loadValidation(draft.id, null, true).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [draft, loadValidation, validationRuns]);

  const startSampleValidation = async (
    /** @type {File | null} */
    reviewFile,
    /** @type {string} */
    comparisonType = "standard_version",
  ) => {
    setBusy("validation");
    try {
      if (!isValidationComparisonType(comparisonType)) {
        throw new Error("不支持的验证目的");
      }
      const saved = await persistDraft();
      if (!reviewFile && !validationSourceId) throw new Error("当前没有可用的样本来源");
      const value = reviewFile
        ? await classificationStandardApi.createReviewStandardValidationRun(
            saved.id,
            reviewFile,
            saved.revision,
            validationSampleSize,
            comparisonType,
          )
        : await classificationStandardApi.createClassificationStandardValidationRun(
            saved.id,
            {
              expected_revision: saved.revision,
              source_result_version_id: validationSourceId,
              sample_size: validationSampleSize,
              comparison_type: comparisonType,
            },
          );
      await loadValidation(saved.id, value.id);
      notify("样本验证已进入队列");
    } catch (error) {
      notify(/** @type {Error} */ (error).message, "error");
    } finally {
      setBusy("");
    }
  };

  const approveSampleValidation = async (
    /** @type {string} */ runId,
    /** @type {string} */ note,
  ) => {
    if (!draft) return;
    setBusy("approval");
    try {
      const value =
        await classificationStandardApi.approveClassificationStandardValidationRun(
          runId,
          {
            expected_revision: draft.revision,
            note,
          },
        );
      await loadValidation(draft.id, value.id);
      notify("当前草稿修订已人工确认，可进入发布确认");
    } catch (error) {
      notify(/** @type {Error} */ (error).message, "error");
    } finally {
      setBusy("");
    }
  };

  const selectValidation = async (/** @type {string} */ runId) => {
    const ownership = requestOwnershipRef.current;
    const draftId = ownership.draftId;
    ownership.runId = runId;
    const generation = ++ownership.foreground;
    ownership.background += 1;
    ownership.loading = false;
    try {
      const selected =
        await classificationStandardApi.classificationStandardValidationRun(runId);
      if (
        generation === ownership.foreground &&
        ownership.draftId === draftId &&
        ownership.runId === runId
      ) {
        setSelectedValidation(selected);
      }
    } catch (error) {
      if (
        generation === ownership.foreground &&
        ownership.draftId === draftId &&
        ownership.runId === runId
      ) {
        notify(/** @type {Error} */ (error).message, "error");
      }
    }
  };

  return {
    validationSources,
    validationRuns,
    selectedValidation,
    validationSourceId,
    validationSampleSize,
    setValidationSourceId,
    setValidationSampleSize,
    loadValidation,
    clearValidation,
    startSampleValidation,
    approveSampleValidation,
    selectValidation,
  };
}
