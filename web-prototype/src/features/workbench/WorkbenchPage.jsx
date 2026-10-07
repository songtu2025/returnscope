import useSWR from "swr";
import "../../styles/workbench.css";

import { Plus, WarningCircle } from "@phosphor-icons/react";
import { PageHeading } from "../../components/SharedUi";
import { workbenchApi } from "../../shared/api/workbenchApi";
import { serverStateKeys } from "../../shared/serverState";
import { WorkbenchActions } from "./WorkbenchActions";
import { WorkbenchOutputs } from "./WorkbenchOutputs";

/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchAction} WorkbenchAction */
/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchOutput} WorkbenchOutput */

/** @param {{onNavigate: (destination: string) => void}} props */
export function WorkbenchPage({ onNavigate }) {
  const { data, error, isLoading, mutate } = useSWR(
    serverStateKeys.workbenchSummary(5),
    () => workbenchApi.summary(5),
  );
  const actions = /** @type {WorkbenchAction[]} */ (data?.actions ?? []);
  const recentOutputs = /** @type {WorkbenchOutput[]} */ (data?.recent_outputs ?? []);
  const hasData = data !== undefined;
  const message =
    error instanceof Error ? error.message : error ? "首页数据读取失败" : "";
  const load = () => mutate();
  const state = { isLoading, hasData, message };

  return (
    <div className="standard-page workbench-page">
      <PageHeading
        eyebrow="运营首页"
        title="首页"
        action={
          <button className="primary-button" onClick={() => onNavigate("task-create")}>
            <Plus size={18} />
            创建分析任务
          </button>
        }
      />

      {!isLoading && message && (
        <WorkbenchError
          title={hasData ? "首页更新失败，当前显示上一次数据" : "首页数据读取失败"}
          message={message}
          onRetry={load}
        />
      )}

      <div className="workbench-grid workbench-focus-grid">
        <WorkbenchActions actions={actions} state={state} onNavigate={onNavigate} />
        <WorkbenchOutputs
          recentOutputs={recentOutputs}
          state={state}
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
