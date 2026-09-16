import { useCallback, useEffect, useRef, useState } from "react";
import "../../styles/workbench.css";

import {
  ArrowRight,
  ChartBar,
  ListChecks,
  Plus,
  WarningCircle,
} from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { routeForTarget } from "../../app/navigation";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { workbenchApi } from "../../shared/api/workbenchApi";

/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchTarget} WorkbenchTarget */
/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchAction} WorkbenchAction */
/** @typedef {import("../../shared/api/workbenchContracts").WorkbenchOutput} WorkbenchOutput */

/** @type {Record<string, string>} */
const ACTION_LABELS = {
  blocked: "阻断",
  failed: "失败",
  review_required: "需复核",
  paused: "已暂停",
  report_running: "报告生成中",
  report_failed: "报告失败",
};

/** @type {Record<string, string>} */
const OUTPUT_LABELS = {
  classification_result: "分类结果",
  derived_result: "复核派生结果",
  dashboard: "分析看板",
  insight_report: "AI 洞察报告",
};

/** @param {WorkbenchTarget} target */
function openTarget(target) {
  const destination = routeForTarget(target);
  if (!destination) return;
  if (target?.action === "review" && destination.page === "classification-results") {
    navigateHash(destination.page, { ...destination.query, tab: "history" });
    return;
  }
  navigateHash(destination.page, destination.query);
}

/** @param {WorkbenchAction} action */
function nextActionLabel(action) {
  if (action.type === "review_required") return "创建复核批次";
  if (action.type === "report_running") return "查看进度";
  if (action.type === "report_failed") return "查看并重试";
  return (
    (action.status ? ACTION_LABELS[action.status] : undefined) ??
    action.status ??
    "查看详情"
  );
}

/** @param {{onNavigate: (destination: string) => void}} props */
export function WorkbenchPage({ onNavigate }) {
  const [state, setState] = useState(
    /** @type {{loading: boolean, error: string, actions: WorkbenchAction[], recentOutputs: WorkbenchOutput[], counts: Record<string, number>}} */ ({
      loading: true,
      error: "",
      actions: [],
      recentOutputs: [],
      counts: {},
    }),
  );
  const controllerRef = useRef(/** @type {AbortController | null} */ (null));
  const generationRef = useRef(0);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    const generation = generationRef.current + 1;
    controllerRef.current = controller;
    generationRef.current = generation;
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const value = await workbenchApi.summary(5, { signal: controller.signal });
      if (generationRef.current !== generation) return;
      setState({
        loading: false,
        error: "",
        actions: value.actions ?? [],
        recentOutputs: value.recent_outputs ?? [],
        counts: value.counts ?? {},
      });
    } catch (error) {
      const requestError =
        error instanceof Error ? error : new Error("首页数据读取失败");
      if (generationRef.current === generation && requestError.name !== "AbortError") {
        setState((current) => ({
          ...current,
          loading: false,
          error: requestError.message,
        }));
      }
    }
  }, []);

  useEffect(() => {
    load();
    return () => {
      generationRef.current += 1;
      controllerRef.current?.abort();
    };
  }, [load]);

  return (
    <div className="standard-page workbench-page">
      <PageHeading
        eyebrow="运营首页"
        title="首页"
        description="集中查看待处理事项、后台任务进度和最近形成的业务产出。"
        action={
          <button className="primary-button" onClick={() => onNavigate("task-create")}>
            <Plus size={18} />
            创建分析任务
          </button>
        }
      />

      {!state.loading && state.error && (
        <WorkbenchError title="首页数据读取失败" message={state.error} onRetry={load} />
      )}

      <div className="workbench-grid workbench-focus-grid">
        <section className="content-card workbench-card workbench-action-card">
          <header>
            <div>
              <b>待处理与后台进度</b>
              <span>阻断、失败、需复核、暂停和报告生成进度，最多显示 5 项</span>
            </div>
            <button
              className="text-button"
              onClick={() => onNavigate("analysis-tasks")}
            >
              查看分析任务 <ArrowRight size={15} />
            </button>
          </header>
          {state.loading ? (
            <InlineLoading label="正在读取待行动事项…" />
          ) : state.error ? null : state.actions.length === 0 ? (
            <EmptyState
              icon={ListChecks}
              title="当前没有待处理事项或后台任务"
              description="阻断、失败、需复核、暂停和报告生成进度会出现在这里。"
            />
          ) : (
            <div className="workbench-action-list">
              {state.actions.map((action) => (
                <button
                  key={`${action.object_type}-${action.object_id}`}
                  onClick={() => openTarget(action.target)}
                >
                  <span className={`workbench-action-type ${action.type}`}>
                    {ACTION_LABELS[action.type] ?? action.type}
                  </span>
                  <span className="workbench-action-copy">
                    <b>{action.title}</b>
                    <small>{action.reason || "未提供原因"}</small>
                    <em>
                      {action.actor?.name || "未提供操作人"} ·{" "}
                      {formatTime(action.updated_at)}
                    </em>
                  </span>
                  <span className="workbench-action-status">
                    {nextActionLabel(action)}
                    <ArrowRight size={15} />
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="content-card workbench-card workbench-output-card">
          <header>
            <div>
              <b>最近产出</b>
              <span>分类结果、分析看板和已发布 AI 洞察报告</span>
            </div>
            <button
              className="text-button"
              onClick={() => onNavigate("classification-results")}
            >
              查看分类结果 <ArrowRight size={15} />
            </button>
          </header>
          {state.loading ? (
            <InlineLoading label="正在读取最近产出…" />
          ) : state.error ? null : state.recentOutputs.length === 0 ? (
            <EmptyState
              icon={ChartBar}
              title="还没有可查看的产出"
              description="完成分析并发布分类结果后，最新产出会集中显示在这里。"
              action={
                <button
                  className="secondary-button"
                  onClick={() => onNavigate("task-create")}
                >
                  <Plus size={16} />
                  创建分析任务
                </button>
              }
            />
          ) : (
            <div className="workbench-output-list">
              {state.recentOutputs.map((output) => (
                <button
                  key={`${output.type}-${output.version_id}`}
                  onClick={() => openTarget(output.target)}
                >
                  <span>
                    <em>{OUTPUT_LABELS[output.type] ?? output.type}</em>
                    <b>{output.title}</b>
                    <small>{formatTime(output.updated_at)}</small>
                  </span>
                  <span>
                    v{output.version_no ?? "-"}
                    <ArrowRight size={15} />
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
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
