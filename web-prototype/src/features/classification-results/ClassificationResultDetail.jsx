import { ClassificationResultDetailView } from "./ClassificationResultDetailView";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";
import { PageLoadingState } from "../../components/SharedUi";
import { createResultDashboard } from "./resultSelectionActions";
import { ResultError } from "./ClassificationResultCommon";
import { useClassificationResultDetailData } from "./useClassificationResultDetailData";
import { api } from "../../api";
import { errorMessage } from "../../shared/api/requestErrors";

/** @typedef {import("./classificationResultDetailContracts").ClassificationResultGroup} ClassificationResultGroup */
/** @typedef {import("./classificationResultDetailContracts").ClassificationResultDetailProps} ClassificationResultDetailProps */

/** @param {ClassificationResultDetailProps} props */
export function ClassificationResultDetail({ route, updateRoute, notify, userId }) {
  const [selectedGroup, setSelectedGroup] = useState(
    /** @type {ClassificationResultGroup | null} */ (null),
  );
  const [orderInput, setOrderInput] = useState(route.orderId);
  const [versionRefreshError, setVersionRefreshError] = useState("");
  const [refreshAttempt, setRefreshAttempt] = useState(0);
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
  useEffect(() => setVersionRefreshError(""), [route.version, route.tab]);
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
      route.version,
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
  } = useClassificationResultDetailData({ route, notify });

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

  useEffect(() => {
    if (!result || error || route.tab === "history" || selectedGroup) return undefined;
    const controller = new AbortController();
    const refresh = () => {
      if (document.visibilityState === "hidden") return;
      api
        .classificationResultVersions(route.version, { signal: controller.signal })
        .then((versions) => {
          if (controller.signal.aborted) return;
          setVersionRefreshError("");
          const latest = versions.find(
            (version) => version.publish_status === "published",
          );
          if (
            latest &&
            latest.version > result.version &&
            latest.version_id !== route.version
          )
            updateRoute({ version: latest.version_id, recordPage: 1 });
        })
        .catch((reason) => {
          if (!controller.signal.aborted) setVersionRefreshError(errorMessage(reason));
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 10000);
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [
    result,
    error,
    route.version,
    route.tab,
    selectedGroup,
    updateRoute,
    refreshAttempt,
  ]);

  if (loading && !result) {
    return (
      <div className="standard-page classification-results-page">
        <button
          className="text-button result-back-button"
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
      recordsError={recordsError}
      retryRecords={retryRecords}
      orderInput={orderInput}
      setOrderInput={setOrderInput}
      selectedGroup={selectedGroup}
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
