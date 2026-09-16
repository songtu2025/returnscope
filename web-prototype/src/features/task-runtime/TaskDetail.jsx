import { useCallback, useEffect, useState } from "react";
import {
  Archive,
  ArrowClockwise,
  ChartBar,
  DotsThreeVertical,
  DownloadSimple,
  GearSix,
  Pause,
  PlayCircle,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api";
import { InfoRow, InlineLoading, Modal } from "../../components/SharedUi";
import { EFFORT_LABELS, STATUS_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";
import { ExecutionPlanSummary } from "../task-planning/ExecutionPlanSummary";
import {
  SegmentCancelDialog,
  SegmentRetryDialog,
  TaskCancelDialog,
  TaskRenameDialog,
  TaskResumeDialog,
} from "./TaskActionDialogs";
import { SegmentBoard } from "./SegmentBoard";

import { FINAL_TASK_STATUSES, taskSummary } from "./taskRegistryPolicy";

const TASK_STAGES = ["准备数据", "Listing 分类", "发布分类版本", "任务结束"];
const DETAIL_TABS = [
  ["execution", "Listing"],
  ["events", "运行日志"],
  ["config", "任务配置"],
];
const TASK_STAGE_INDEX = {
  准备数据: 0,
  语义分析: 1,
  "Listing 分类": 1,
  生成结果: 2,
  发布分类版本: 2,
  模型服务异常: 1,
  分析完成: 3,
  任务结束: 3,
};

function taskStageLabel(stage) {
  if (/模型服务/.test(stage || "")) return "模型服务异常";
  if (TASK_STAGE_INDEX[stage] != null) return TASK_STAGES[TASK_STAGE_INDEX[stage]];
  if (/发布|生成结果/.test(stage || "")) return TASK_STAGES[2];
  if (/分类|语义/.test(stage || "")) return TASK_STAGES[1];
  if (/完成|结束|取消|失败/.test(stage || "")) return TASK_STAGES[3];
  return TASK_STAGES[0];
}

function eventListing(task, event) {
  const segmentId = event.data?.segment_id;
  if (!segmentId) return "";
  const segment = task.segments?.find((item) => item.id === segmentId);
  return segment?.scope?.listing ?? "";
}

function TaskEventList({ task, events }) {
  const [visibleCount, setVisibleCount] = useState(100);
  const values = events.slice(-visibleCount).reverse();
  return (
    <div className="event-log">
      {values.length === 0 && <p className="muted-line">暂无运行动态。</p>}
      {values.map((event) => {
        const listing = eventListing(task, event);
        const message = listing
          ? event.message.replace(/^Listing\s*/, "")
          : event.message;
        return (
          <div key={event.id}>
            <time>{formatTime(event.created_at)}</time>
            <span className={classNames("event-dot", event.event_type)} />
            <p>
              <b>
                {listing
                  ? `${listing} · ${taskStageLabel(event.stage)}`
                  : taskStageLabel(event.stage)}
              </b>
              {message}
              {event.data?.before?.title && (
                <small>
                  原值：{event.data.before.title}
                  <br />
                  新值：{event.data.after.title}
                  <br />
                  原因：{event.data.note}
                </small>
              )}
              {event.data?.before?.status && (
                <small>
                  原状态：
                  {STATUS_LABELS[event.data.before.status] ?? event.data.before.status}
                  <br />
                  新状态：
                  {STATUS_LABELS[event.data.after.status] ?? event.data.after.status}
                  {event.data.note && (
                    <>
                      <br />
                      原因：{event.data.note}
                    </>
                  )}
                </small>
              )}
              {event.actor_name && <small>操作人：{event.actor_name}</small>}
            </p>
          </div>
        );
      })}
      {events.length > visibleCount && (
        <button
          className="secondary-button"
          onClick={() => setVisibleCount((count) => count + 100)}
        >
          加载更早日志（已显示 {values.length} / {events.length} 条）
        </button>
      )}
    </div>
  );
}

export function TaskDetail({
  task,
  focusSegmentId,
  events,
  onViewClassification,
  actionError,
  onClearActionError,
  onRename,
  onArchive,
  onCancel,
  onPause,
  onResume,
  onRetry,
  onRetrySegment,
  onRetryResultPublish,
  onSegmentAction,
  onParallelism,
  onReorderSegments,
  onPreflightReplan,
  onReplan,
}) {
  const [renameOpen, setRenameOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [retrySegment, setRetrySegment] = useState(null);
  const [cancelSegment, setCancelSegment] = useState(null);
  const [replanOpen, setReplanOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("execution");
  const [listingFilter, setListingFilter] = useState("all");
  const summary = taskSummary(task);
  const isActive = ["queued", "running", "paused"].includes(task.status);
  useEffect(() => {
    if (focusSegmentId) {
      setActiveTab("execution");
      setListingFilter("all");
    }
  }, [focusSegmentId]);
  const showListings = (filter) => {
    setListingFilter(filter);
    setActiveTab("execution");
  };
  const hasUnfinishedSegments = task.segments?.some((segment) =>
    [
      "cancelled",
      "not_started",
      "running",
      "queued",
      "retry_pending",
      "paused",
    ].includes(segment.status),
  );
  const executableSegments =
    task.segments?.filter((segment) => segment.agent_key !== "unknown") ?? [];
  const modelServiceIssue = executableSegments.find(
    (segment) =>
      ["paused", "failed", "running"].includes(segment.status) &&
      Number(segment.model_failures || 0) >= 3 &&
      segment.error,
  );
  const remainingSegments = summary.remaining;
  const firstStandard = executableSegments.find((segment) => segment.standard_name);

  return (
    <>
      <header className="task-command-header">
        <div className="task-detail-summary">
          <div className="task-title-row">
            <h2>{task.title}</h2>
            <span className={classNames("task-status-badge", task.status)}>
              {summary.statusLabel}
            </span>
          </div>
          <p>
            {task.store || task.dataset_name} · {task.owner_name} ·{" "}
            {formatTime(task.created_at)}
          </p>
        </div>
        <div className="detail-actions">
          {(task.status === "blocked" ||
            (task.status === "partial" && remainingSegments > 0)) && (
            <button className="primary-button" onClick={() => setReplanOpen(true)}>
              <ArrowClockwise size={17} />
              重新预检 / 规划
            </button>
          )}
          {["paused", "cancelled"].includes(task.status) && hasUnfinishedSegments && (
            <button className="primary-button" onClick={() => setResumeOpen(true)}>
              <PlayCircle size={17} />
              {task.status === "cancelled" ? "重新排队未完成" : "继续未完成"}
            </button>
          )}
          {["queued", "running"].includes(task.status) && (
            <button className="primary-button" onClick={onPause}>
              <Pause size={17} /> 暂停未完成
            </button>
          )}
          {task.status === "failed" && (
            <button className="primary-button" onClick={onRetry}>
              <ArrowClockwise size={17} /> 重新运行
            </button>
          )}
          {summary.generated > 0 && (
            <button
              className={
                task.status === "completed" ? "primary-button" : "secondary-button"
              }
              onClick={() => showListings("delivered")}
            >
              <ChartBar size={17} /> 查看已有结果
            </button>
          )}
          <details className="task-more-actions">
            <summary aria-label="更多任务操作" title="更多任务操作">
              <DotsThreeVertical size={19} />
            </summary>
            <div>
              {task.result_file_path && (
                <a href={api.downloadUrl(task.id)}>
                  <DownloadSimple size={16} />
                  {task.status === "cancelled" ? "下载部分结果" : "下载结果"}
                </a>
              )}
              <button onClick={() => setRenameOpen(true)}>
                <GearSix size={16} /> 修改名称
              </button>
              {task.status === "completed" && (
                <button onClick={onRetry}>
                  <ArrowClockwise size={16} /> 再次运行
                </button>
              )}
              {(task.archived_at || FINAL_TASK_STATUSES.includes(task.status)) && (
                <button onClick={onArchive}>
                  <Archive size={16} />
                  {task.archived_at ? "恢复任务" : "归档任务"}
                </button>
              )}
              {["queued", "running", "paused"].includes(task.status) && (
                <button className="danger" onClick={() => setCancelOpen(true)}>
                  <X size={16} />
                  取消未完成
                </button>
              )}
            </div>
          </details>
        </div>
      </header>

      {actionError && !retrySegment && (
        <div className="task-action-error" role="alert">
          <WarningCircle size={18} />
          <span>{actionError}</span>
          <button onClick={onClearActionError}>关闭</button>
        </div>
      )}

      {["failed", "blocked", "partial"].includes(task.status) && task.message && (
        <section className="task-action-banner" role="status">
          <WarningCircle size={19} />
          <div>
            <b>{summary.issueDescription}</b>
            <p>{task.message}</p>
            <small>查看下方 Listing 的原因和可执行操作；已生成的结果仍可查看。</small>
          </div>
        </section>
      )}

      {modelServiceIssue && (
        <div className="task-model-service-alert" role="alert">
          <WarningCircle size={20} weight="fill" />
          <div>
            <b>
              {task.status === "paused" && task.pause_requested
                ? "模型服务异常，任务已自动暂停"
                : task.status === "paused"
                  ? "模型服务异常，任务已暂停"
                  : task.status === "failed"
                    ? "模型服务异常，执行已停止"
                    : "模型服务异常，请检查连接与运行日志"}
            </b>
            <span>{modelServiceIssue.error}</span>
          </div>
          <small>
            成功 {modelServiceIssue.model_calls || 0} · 失败{" "}
            {modelServiceIssue.model_failures || 0} · 缓存{" "}
            {modelServiceIssue.cache_hits || 0}
          </small>
        </div>
      )}

      <section className="task-overview-band" aria-label="任务运行总览">
        <div className="task-overview-metrics">
          <div className="primary">
            <span>评论处理进度</span>
            <b>{Math.round(task.progress_percent || 0)}%</b>
            <small>
              {(task.progress_current || 0).toLocaleString()} /{" "}
              {(task.progress_total || 0).toLocaleString()} 组评论
            </small>
          </div>
          <div>
            <span>已生成结果</span>
            <b>
              {summary.generated}
              <small> / {summary.total} 个 Listing</small>
            </b>
            <small>{summary.resultDescription || "分析完成后生成结果"}</small>
          </div>
          <div>
            <span>需要处理</span>
            <b>
              {summary.issues || (summary.needsAttention ? "待确认" : 0)}
              {(!summary.needsAttention || summary.issues > 0) && (
                <small> 个 Listing</small>
              )}
            </b>
            {summary.needsAttention ? (
              <button
                className="task-inline-action"
                onClick={() => showListings("attention")}
              >
                查看需处理事项
              </button>
            ) : (
              <small>
                {task.status === "paused"
                  ? "未完成部分已暂停，可随时继续"
                  : "暂无需介入的问题"}
              </small>
            )}
          </div>
        </div>
      </section>

      <div className="task-detail-tabs" role="tablist" aria-label="任务详情视图">
        {DETAIL_TABS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            id={`task-tab-${value}`}
            aria-controls="task-view-panel"
            aria-selected={activeTab === value}
            className={activeTab === value ? "active" : ""}
            onClick={() => {
              setActiveTab(value);
              if (value === "execution") setListingFilter("all");
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <section
        className="task-detail-tab-panel"
        id="task-view-panel"
        role="tabpanel"
        aria-labelledby={`task-tab-${activeTab}`}
      >
        {activeTab === "execution" && (
          <SegmentBoard
            key={listingFilter}
            initialFilter={listingFilter}
            task={task}
            focusSegmentId={listingFilter === "all" ? focusSegmentId : null}
            onRetry={(segment) => {
              onClearActionError();
              setRetrySegment(segment);
            }}
            onRetryPublish={onRetryResultPublish}
            onCancel={(segment) => setCancelSegment(segment)}
            onAction={onSegmentAction}
            onParallelism={onParallelism}
            onReorder={onReorderSegments}
            onViewClassification={onViewClassification}
            onResumeUnfinished={() => setResumeOpen(true)}
          />
        )}

        {activeTab === "events" && (
          <section className="task-secondary-section full-event-section">
            <header>
              <div>
                <h3>完整运行日志</h3>
                <p>来自后台执行器的真实事件，按时间倒序排列。</p>
              </div>
              <span className="live-tag">
                {isActive && <i />}
                {isActive ? "实时更新" : "完整记录"}
              </span>
            </header>
            <TaskEventList task={task} events={events} />
          </section>
        )}

        {activeTab === "config" && (
          <section className="task-secondary-section task-config-panel">
            <header>
              <div>
                <h3>任务配置</h3>
                <p>任务运行期间始终使用创建时固化的版本。</p>
              </div>
            </header>
            <div className="task-config-body">
              <InfoRow label="分类标准" value={firstStandard?.standard_name || "—"} />
              <InfoRow label="并行数" value={task.max_parallel_segments ?? 3} />
              <InfoRow label="任务 ID" value={task.id} />
              <InfoRow
                label="退货明细"
                value={`${task.dataset_name || "—"} · v${task.dataset_version || "—"}`}
              />
              <InfoRow
                label="产品信息"
                value={`${task.product_name || "—"} · v${task.product_version || "—"}`}
              />
              <InfoRow
                label="模型配置"
                value={`${task.connection_name || "—"} · #${task.config_version || "—"}`}
              />
              <InfoRow
                label="主模型"
                value={`${task.primary_model || "—"} · ${EFFORT_LABELS[task.primary_effort] ?? task.primary_effort ?? "—"}`}
              />
            </div>
          </section>
        )}
      </section>

      {renameOpen && (
        <TaskRenameDialog
          task={task}
          onClose={() => setRenameOpen(false)}
          onSave={async (payload) => {
            const saved = await onRename(payload);
            if (saved) setRenameOpen(false);
          }}
        />
      )}
      {cancelOpen && (
        <TaskCancelDialog
          task={task}
          onClose={() => setCancelOpen(false)}
          onSave={async (payload) => {
            const saved = await onCancel(payload);
            if (saved) setCancelOpen(false);
          }}
        />
      )}
      {resumeOpen && (
        <TaskResumeDialog
          task={task}
          onClose={() => setResumeOpen(false)}
          onSave={async (payload) => {
            const saved = await onResume(payload);
            if (saved) setResumeOpen(false);
          }}
        />
      )}
      {retrySegment && (
        <SegmentRetryDialog
          task={task}
          segment={retrySegment}
          error={actionError}
          onClose={() => setRetrySegment(null)}
          onSave={async (payload) => {
            const saved = await onRetrySegment(retrySegment.segment_key, payload);
            if (saved) setRetrySegment(null);
          }}
        />
      )}
      {cancelSegment && (
        <SegmentCancelDialog
          task={task}
          segment={cancelSegment}
          onClose={() => setCancelSegment(null)}
          onSave={async (note) => {
            const saved = await onSegmentAction(
              cancelSegment.segment_key,
              "cancel",
              note,
            );
            if (saved) setCancelSegment(null);
          }}
        />
      )}
      {replanOpen && (
        <TaskReplanDialog
          task={task}
          onClose={() => setReplanOpen(false)}
          onPreflight={onPreflightReplan}
          onSave={async (payload) => {
            const saved = await onReplan(payload);
            if (saved) setReplanOpen(false);
          }}
        />
      )}
    </>
  );
}

function TaskReplanDialog({ task, onClose, onPreflight, onSave }) {
  const [plan, setPlan] = useState(null);
  const [policy, setPolicy] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const loadPlan = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const value = await onPreflight({ product_version_id: task.product_version_id });
      setPlan(value);
      setPolicy(value.blocked_count > 0 ? "" : "block_all");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [onPreflight, task.product_version_id]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  const submit = async (event) => {
    event.preventDefault();
    if (!plan || !policy) return;
    setSaving(true);
    try {
      await onSave({
        product_version_id: task.product_version_id,
        expected_revision: task.revision,
        plan_hash: plan.plan_hash,
        unresolved_policy: policy,
        reason,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal eyebrow="任务恢复" title="重新预检并规划" onClose={onClose}>
      <form className="modal-form replan-form" onSubmit={submit}>
        {loading && <InlineLoading label="正在重新预检执行计划…" />}
        {error && (
          <div className="plan-state error" role="alert">
            <WarningCircle size={19} />
            <span>{error}</span>
            <button type="button" onClick={loadPlan}>
              重新预检
            </button>
          </div>
        )}
        {plan && (
          <ExecutionPlanSummary
            plan={plan}
            policy={policy}
            onPolicyChange={setPolicy}
          />
        )}
        <label>
          重新规划原因
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength="500"
            rows="3"
            placeholder="必填，说明本次重新规划依据"
            required
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button
            className="primary-button"
            disabled={saving || loading || !plan || !policy || !reason.trim()}
          >
            {saving ? "正在更新…" : "提交新执行计划"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
