import { useCallback, useEffect, useState } from "react";

import { classificationStandardApi } from "../../shared/api/classificationStandardApi";

/** @typedef {{id: string, revision: number}} ValidationDraft */
/** @typedef {{result_version_id: string}} ValidationSource */
/** @typedef {{id: string, status: string}} ValidationRun */

/**
 * @typedef {object} ValidationControllerOptions
 * @property {ValidationDraft | null} draft
 * @property {(message: string, tone?: string) => void} notify
 * @property {() => Promise<ValidationDraft>} persistDraft
 * @property {(value: string) => void} setBusy
 */

/** @param {ValidationControllerOptions} options */
export function useClassificationStandardValidationController({
  draft,
  notify,
  persistDraft,
  setBusy,
}) {
  const [validationSources, setValidationSources] = useState(
    /** @type {ValidationSource[]} */ ([]),
  );
  const [validationRuns, setValidationRuns] = useState(
    /** @type {ValidationRun[]} */ ([]),
  );
  const [selectedValidation, setSelectedValidation] = useState(
    /** @type {ValidationRun | null} */ (null),
  );
  const [validationSourceId, setValidationSourceId] = useState("");
  const [validationSampleSize, setValidationSampleSize] = useState(20);

  const loadValidation = useCallback(
    async (
      /** @type {string} */ draftId,
      /** @type {string | null} */ preferredRunId = null,
    ) => {
      /** @type {[ValidationSource[], ValidationRun[]]} */
      const [sources, runs] = await Promise.all([
        classificationStandardApi.classificationStandardValidationSources(draftId),
        classificationStandardApi.classificationStandardValidationRuns(draftId),
      ]);
      setValidationSources(sources);
      setValidationRuns(runs);
      setValidationSourceId((current) =>
        sources.some((source) => source.result_version_id === current)
          ? current
          : sources[0]?.result_version_id || "",
      );
      const selectedRunId = preferredRunId || runs[0]?.id;
      setSelectedValidation(
        selectedRunId
          ? await classificationStandardApi.classificationStandardValidationRun(
              selectedRunId,
            )
          : null,
      );
    },
    [],
  );

  const clearValidation = useCallback(() => {
    setValidationSources([]);
    setValidationRuns([]);
    setSelectedValidation(null);
    setValidationSourceId("");
  }, []);

  useEffect(() => {
    const active = validationRuns.some((run) =>
      ["queued", "running"].includes(run.status),
    );
    if (!draft || !active) return undefined;
    const timer = window.setInterval(() => {
      loadValidation(draft.id, selectedValidation?.id).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [draft, loadValidation, selectedValidation?.id, validationRuns]);

  const startSampleValidation = async (
    /** @type {File | null} */
    reviewFile,
    /** @type {string} */
    comparisonType = "standard_version",
  ) => {
    setBusy("validation");
    try {
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
    try {
      setSelectedValidation(
        await classificationStandardApi.classificationStandardValidationRun(runId),
      );
    } catch (error) {
      notify(/** @type {Error} */ (error).message, "error");
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
