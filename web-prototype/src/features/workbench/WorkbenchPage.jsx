import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import useSWR from "swr";
import "../../styles/workbench.css";

import { Plus, WarningCircle } from "@phosphor-icons/react";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
import { workbenchApi } from "../../shared/api/workbenchApi";
import { serverStateKeys } from "../../shared/serverState";
import { WorkbenchActions } from "./WorkbenchActions";
import { WorkbenchOutputs } from "./WorkbenchOutputs";

/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchAction} WorkbenchAction */
/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchOutput} WorkbenchOutput */

/** @param {{onNavigate: (destination: string) => void}} props */
export function WorkbenchPage({ onNavigate }) {
  const { data, error, isLoading, isValidating, mutate } = useSWR(
    serverStateKeys.workbenchSummary(5),
    () => workbenchApi.summary(5),
    MANAGED_REFRESH_OPTIONS,
  );
  useDataRefresh(() => mutate(), { loading: isLoading || isValidating });
  const actions = /** @type {WorkbenchAction[]} */ (data?.actions ?? []);
  const recentOutputs = /** @type {WorkbenchOutput[]} */ (data?.recent_outputs ?? []);
  const hasData = data !== undefined;
  const message =
    error instanceof Error ? error.message : error ? "首页数据读取失败" : "";
  const load = () =>
    mutate((current) => current, { revalidate: true, throwOnError: false });

  return (
    <div className="standard-page workbench-page">
      <PageHeading
        title="首页"
        action={
          <>
            <InlineLoading
              scope={hasData ? "local" : "page"}
              label="读取首页…"
              compact
              active={isLoading || isValidating}
            />
            <button
              className="primary-button"
              onClick={() => onNavigate("task-create")}
            >
              <Plus size={18} />
              创建分析任务
            </button>
          </>
        }
      />

      {!isLoading && message && (
        <WorkbenchError
          title={hasData ? "首页更新失败，当前显示上一次数据" : "首页数据读取失败"}
          message={message}
          onRetry={load}
        />
      )}

      <div
        className="workbench-grid workbench-focus-grid"
        aria-busy={isLoading || isValidating}
      >
        <WorkbenchActions actions={actions} hasData={hasData} onNavigate={onNavigate} />
        <WorkbenchOutputs
          recentOutputs={recentOutputs}
          hasData={hasData}
          onNavigate={onNavigate}
        />
      </div>
    </div>
  );
}

/** @param {{title: string, message: string, onRetry: () => void}} props */
function WorkbenchError({ title, message, onRetry }) {
  return (
    <div className="plan-state error workbench-local-error" role="alert">
      <WarningCircle size={20} />
      <div>
        <b>{title}</b>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry}>
        重新加载
      </button>
    </div>
  );
}
