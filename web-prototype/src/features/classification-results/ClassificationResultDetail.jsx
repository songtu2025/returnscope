import { ClassificationResultDetailView } from "./ClassificationResultDetailView";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { PageLoadingState } from "../../components/SharedUi";
import { createResultDashboard } from "./resultSelectionActions";
import { ResultError } from "./ClassificationResultCommon";
import { useClassificationResultDetailData } from "./useClassificationResultDetailData";

/** @typedef {import("./classificationResultDetailContracts").ClassificationResultGroup} ClassificationResultGroup */
/** @typedef {import("./classificationResultDetailContracts").ClassificationResultDetailProps} ClassificationResultDetailProps */

/** @param {ClassificationResultDetailProps} props */
export function ClassificationResultDetail({ route, updateRoute, notify, userId }) {
  const [selectedGroup, setSelectedGroup] = useState(
    /** @type {ClassificationResultGroup | null} */ (null),
  );
  const [orderInput, setOrderInput] = useState(route.orderId);
  const evidenceTriggerRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const closeEvidence = useCallback(() => setSelectedGroup(null), []);

  const createDashboardFromResult = () => {
    if (!result) return;
    createResultDashboard(userId, result);
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
    [route.orderId, route.problem, route.productName, route.productSku, route.version],
  );

  const {
    result,
    summary,
    records,
    drilldowns,
    loading,
    recordsLoading,
    error,
    retry,
  } = useClassificationResultDetailData({ route, notify });

  if (loading && !result) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button"
          onClick={() => updateRoute({ version: "" })}
        >
          <ArrowLeft size={17} /> 返回分类结果池
        </button>
        <PageLoadingState label="正在读取分类结果详情…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button"
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
    setSelectedGroup(group);
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
      orderInput={orderInput}
      setOrderInput={setOrderInput}
      selectedGroup={selectedGroup}
      closeEvidence={closeEvidence}
      openEvidence={openEvidence}
      evidenceTriggerRef={evidenceTriggerRef}
      createDashboardFromResult={createDashboardFromResult}
      openOrderRecords={openOrderRecords}
      loading={loading}
      error={error}
      retry={retry}
    />
  );
}
