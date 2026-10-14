import { ClassificationResultDetailView } from "./ClassificationResultDetailView";
import { useEffect, useRef, useState } from "react";
import { useEvidenceNavigation } from "./useEvidenceNavigation";
import { ArrowLeft } from "@phosphor-icons/react";
import { PageLoadingState } from "../../components/SharedUi";
import { createResultDashboard } from "./resultSelectionActions";
import { ResultError } from "./ClassificationResultCommon";
import { useClassificationResultDetailData } from "./useClassificationResultDetailData";
import { useLatestResult } from "./useLatestResult";

/** @typedef {import("./classificationResultDetailContracts").ClassificationResultGroup} ClassificationResultGroup */
/** @typedef {import("./classificationResultDetailContracts").ClassificationResultDetailProps} ClassificationResultDetailProps */

/** @param {ClassificationResultDetailProps} props */
export function ClassificationResultDetail({ route, updateRoute, notify, userId }) {
  const [selectedGroup, setSelectedGroup] = useState(
    /** @type {ClassificationResultGroup | null} */ (null),
  );
  const [orderInput, setOrderInput] = useState(route.orderId);
  const [refreshAttempt, setRefreshAttempt] = useState(0);
  const evidenceTriggerRef = useRef(/** @type {HTMLButtonElement | null} */ (null));

  const createDashboardFromResult = () => {
    if (!result) return;
    createResultDashboard(userId, result, route);
  };

  const openOrderRecords = () => {
    updateRoute({ tab: "records", action: "" });
    window.setTimeout(
      () => document.getElementById("classification-order-records")?.scrollIntoView(),
      0,
    );
  };

  useEffect(() => setOrderInput(route.orderId), [route.orderId]);
  useEffect(
    () => setSelectedGroup(null),
    [
      route.orderId,
      route.problem,
      route.productName,
      route.productSku,
      route.recordQualityStatus,
      route.commentStatus,
      route.systemRerunRequired,
    ],
  );

  const {
    result,
    summary,
    records,
    drilldowns,
    loading,
    recordsLoading,
    recordsError,
    retryRecords,
    error,
    retry,
  } = useClassificationResultDetailData({
    route,
    notify,
    protectedOperation: Boolean(selectedGroup),
  });
  const evidenceNavigation = useEvidenceNavigation({
    route,
    records,
    group: selectedGroup,
    setGroup: setSelectedGroup,
    updateRoute,
    notify,
  });
  const closeEvidence = () => {
    const row = [...document.querySelectorAll(".result-record-row")].find(
      (element) =>
        element.getAttribute("data-feedback-source") ===
        selectedGroup?.record.source_record_id,
    );
    const trigger =
      row?.querySelector("button") ?? document.querySelector(".result-back-button");
    if (trigger instanceof HTMLButtonElement) evidenceTriggerRef.current = trigger;
    evidenceNavigation.close();
  };

  useEffect(() => {
    if (!records || recordsLoading || recordsError) return;
    const lastPage = Math.max(Math.ceil(records.total / route.pageSize), 1);
    if (route.recordPage > lastPage) updateRoute({ recordPage: lastPage });
  }, [
    records,
    recordsLoading,
    recordsError,
    route.pageSize,
    route.recordPage,
    updateRoute,
  ]);

  const versionRefreshError = useLatestResult({
    route,
    result,
    protectedOperation: Boolean(selectedGroup),
    updateRoute,
    refreshAttempt,
  });

  if (loading && !result) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button page-loading-navigation"
          onClick={() => updateRoute({ version: "" })}
        >
          <ArrowLeft size={17} /> 返回分类结果池
        </button>
        <PageLoadingState title="分类结果" label="正在读取分类结果详情…" />
      </div>
    );
  }

  if (error && !result) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button page-loading-navigation"
          onClick={() => updateRoute({ version: "" })}
        >
          <ArrowLeft size={17} /> 返回结果池
        </button>
        <ResultError message={error} onRetry={retry} />
      </div>
    );
  }

  if (!result) return null;

  /**
   * @param {ClassificationResultGroup} group
   * @returns {(trigger: HTMLButtonElement) => void}
   */
  const openEvidence = (group) => (trigger) => {
    evidenceTriggerRef.current = trigger;
    evidenceNavigation.open(group);
  };

  return (
    <ClassificationResultDetailView
      route={route}
      updateRoute={updateRoute}
      notify={notify}
      userId={userId}
      result={result}
      summary={summary}
      records={records}
      drilldowns={drilldowns}
      recordsLoading={recordsLoading}
      recordsError={recordsError}
      retryRecords={retryRecords}
      orderInput={orderInput}
      setOrderInput={setOrderInput}
      selectedGroup={selectedGroup}
      evidenceNavigation={evidenceNavigation}
      closeEvidence={closeEvidence}
      openEvidence={openEvidence}
      evidenceTriggerRef={evidenceTriggerRef}
      createDashboardFromResult={createDashboardFromResult}
      openOrderRecords={openOrderRecords}
      loading={loading}
      error={error || versionRefreshError}
      retry={() => {
        retry();
        setRefreshAttempt((current) => current + 1);
      }}
    />
  );
}
