import { useCallback, useEffect, useState } from "react";
import {
  ArrowClockwise,
  CaretRight,
  ChartBar,
  Check,
  CheckCircle,
  DownloadSimple,
  GearSix,
  Pause,
  PlayCircle,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import { api } from "../../api";
import { CardHeading, InfoRow, InlineLoading, Modal } from "../../components/SharedUi";
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
import {
  isLegacyResult,
  isPublishedResult,
  resultPublishStatus,
} from "./taskSegmentPolicy";

const TASK_STAGES = ["准备数据", "Listing 分类", "发布分类版本", "任务结束"];
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

export function TaskDetail({
  task,
  focusSegmentId,
  events,
  onViewClassification,
  actionError,
  onClearActionError,
  onRename,
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
  const stages = TASK_STAGES;
  const terminalTask = ["completed", "failed", "cancelled", "partial"].includes(
    task.status,
  );
  const currentStage = Math.max(
    TASK_STAGE_INDEX[task.stage] ?? 0,
    terminalTask ? 3 : 0,
  );
  const pendingReviews = Math.max(
    (task.metrics?.review_count ?? 0) - (task.metrics?.review_resolved ?? 0),
    0,
  );
  const isActive = ["queued", "running", "paused"].includes(task.status);
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
    (segment) => Number(segment.model_failures || 0) >= 3 && segment.error,
  );
  const completedSegments = executableSegments.filter((segment) =>
    ["completed", "completed_with_errors"].includes(segment.status),
  );
  const deliveredSegments = completedSegments.filter(
    (segment) => isPublishedResult(segment) || isLegacyResult(segment),
  );
  const publishingSegments = completedSegments.filter(
    (segment) => resultPublishStatus(segment) === "publishing",
  );
  const activeSegments = executableSegments.filter((segment) =>
    ["running", "pause_pending", "cancel_pending"].includes(
      segment.display_status || segment.status,
    ),
  );
  const waitingSegments = Math.max(
    executableSegments.length -
      deliveredSegments.length -
      publishingSegments.length -
      activeSegments.length,
    0,
  );
  const remainingSegments =
    waitingSegments + activeSegments.length + publishingSegments.length;
  const deliveredWithIssues =
    task.status === "partial" &&
    remainingSegments === 0 &&
    deliveredSegments.some((segment) => segment.status === "completed_with_errors");
  const nextAction =
    {
      queued: "等待后台领取",
      running: "后台继续执行，需要时可安全暂停",
      paused: "继续全部后恢复执行",
      blocked: "重新预检后继续",
      partial: deliveredWithIssues
        ? "处理待复核与模型异常记录"
        : "重新预检并处理未完成 Listing",
      completed: "查看或下载分类结果",
      failed: "检查失败片段后重试",
      cancelled: hasUnfinishedSegments ? "重新排队未完成 Listing" : "查看部分结果",
    }[task.status] ?? "查看执行详情";
  return (
    <>
      <header className="task-detail-header">
        <div className="task-detail-summary">
          <div className="task-title-row">
            <h2>{task.title}</h2>
          </div>
          <p>
            {task.owner_name} · {formatTime(task.created_at)} · 已交付{" "}
            {deliveredSegments.length}/{executableSegments.length} · 剩余{" "}
            {remainingSegments} 个 Listing · 待复核 {pendingReviews.toLocaleString()}
          </p>
          <span className="task-next-action">下一步：{nextAction}</span>
        </div>
        <div className="detail-actions">
          {task.result_file_path && (
            <a className="primary-button" href={api.downloadUrl(task.id)}>
              <DownloadSimple size={18} />
              {task.status === "cancelled" ? "下载部分结果" : "下载结果"}
            </a>
          )}
          {(task.status === "blocked" ||
            (task.status === "partial" && remainingSegments > 0)) && (
            <button className="primary-button" onClick={() => setReplanOpen(true)}>
              <ArrowClockwise size={17} />
              重新预检 / 规划
            </button>
          )}
          {task.status === "completed" && (
            <button className="secondary-button" onClick={onRetry}>
              <ArrowClockwise size={17} />
              再次运行
            </button>
          )}
          {["paused", "cancelled"].includes(task.status) && hasUnfinishedSegments && (
            <button className="secondary-button" onClick={() => setResumeOpen(true)}>
              <PlayCircle size={17} />
              {task.status === "cancelled" ? "重新排队未完成" : "继续全部"}
            </button>
          )}
          {["queued", "running"].includes(task.status) && (
            <button className="secondary-button" onClick={onPause}>
              <Pause size={17} />
              暂停全部
            </button>
          )}
          {["queued", "running", "paused"].includes(task.status) && (
            <button className="danger-button" onClick={() => setCancelOpen(true)}>
              <X size={17} />
              取消未完成
            </button>
          )}
          <button
            className="secondary-button task-rename-action"
            onClick={() => setRenameOpen(true)}
            aria-label="修改名称"
            title="修改名称"
          >
            <GearSix size={17} />
          </button>
        </div>
      </header>
      {actionError && !retrySegment && (
        <div className="task-action-error" role="alert">
          <WarningCircle size={18} />
          <span>{actionError}</span>
          <button onClick={onClearActionError}>关闭</button>
        </div>
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
                  : "模型服务异常，正在自动重试"}
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
      {isActive && (
        <section className="progress-hero">
          <div className="progress-copy">
            <span>当前阶段</span>
            <h3>{taskStageLabel(task.stage)}</h3>
            <p>{task.message}</p>
          </div>
          <div className="progress-number">
            <strong>{Math.round(task.progress_percent)}</strong>
            <span>%</span>
            <small>
              {task.progress_current}/{task.progress_total || "—"}
            </small>
          </div>
          <div className="hero-progress">
            <span style={{ width: `${task.progress_percent}%` }} />
          </div>
        </section>
      )}
      <div className="stage-strip">
        {stages.map((stage, index) => (
          <div
            key={stage}
            className={classNames(
              index <= currentStage && "active",
              index < currentStage && "done",
            )}
          >
            <span>{index < currentStage ? <Check size={14} /> : index + 1}</span>
            <b>{stage}</b>
          </div>
        ))}
      </div>
      {task.status === "cancelled" && deliveredSegments.some(isPublishedResult) && (
        <div className="task-result-retained" role="status">
          <CheckCircle size={18} />
          <div>
            <b>批量任务已取消，已完成 Listing 的分类结果仍然保留</b>
            <span>可在下方对应 Listing 行查看分类结果，或进入分类结果池继续处理。</span>
          </div>
        </div>
      )}
      <SegmentBoard
        task={task}
        focusSegmentId={focusSegmentId}
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
      />
      <div className="task-detail-grid">
        <section className="content-card event-card">
          <CardHeading
            title="运行日志"
            note="来自后台执行器的真实事件"
            action={
              <span className="live-tag">
                {isActive && <i />}
                {isActive ? "实时更新" : "完整记录"}
              </span>
            }
          />
          <div className="event-log">
            {events.length === 0 && <p className="muted-line">等待新的运行事件…</p>}
            {events
              .slice()
              .reverse()
              .map((event) => {
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
                          {STATUS_LABELS[event.data.before.status] ??
                            event.data.before.status}
                          <br />
                          新状态：
                          {STATUS_LABELS[event.data.after.status] ??
                            event.data.after.status}
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
          </div>
        </section>
        <aside className="task-inspector">
          <section className="content-card delivery-card">
            <CardHeading title="交付进度" note="完成一个 Listing 即可查看" />
            <div className="delivery-counts">
              <div>
                <b>{deliveredSegments.length}</b>
                <span>已交付</span>
              </div>
              <div>
                <b>{activeSegments.length + publishingSegments.length}</b>
                <span>运行中</span>
              </div>
              <div>
                <b>{waitingSegments}</b>
                <span>待处理</span>
              </div>
            </div>
            {deliveredSegments.some(isPublishedResult) ? (
              <button
                className="primary-button delivery-button"
                onClick={() =>
                  onViewClassification(deliveredSegments.find(isPublishedResult))
                }
              >
                <ChartBar size={17} />
                查看首个已交付分类结果
              </button>
            ) : deliveredSegments.some(isLegacyResult) ? (
              <a
                className="primary-button delivery-button"
                href={api.segmentDownloadUrl(
                  task.id,
                  deliveredSegments.find(isLegacyResult).segment_key,
                )}
              >
                <DownloadSimple size={17} />
                下载旧结果
              </a>
            ) : (
              <p className="muted-line">
                首个 Listing 发布后，分类结果入口会显示在这里。
              </p>
            )}
          </section>
          <details className="content-card task-config-details">
            <summary>
              <div>
                <b>任务配置</b>
                <span>
                  数据 v{task.dataset_version} · {task.primary_model}
                </span>
              </div>
              <CaretRight size={16} />
            </summary>
            <div className="task-config-body">
              <InfoRow
                label="退货明细"
                value={`${task.dataset_name} · v${task.dataset_version}`}
              />
              <InfoRow
                label="产品信息"
                value={`${task.product_name} · v${task.product_version}`}
              />
              <InfoRow
                label="模型配置"
                value={`${task.connection_name} · #${task.config_version}`}
              />
              <InfoRow
                label="主模型"
                value={`${task.primary_model} · ${EFFORT_LABELS[task.primary_effort] ?? task.primary_effort}`}
              />
            </div>
          </details>
        </aside>
      </div>
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
