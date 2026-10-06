/** @typedef {import("./taskCreateContracts").TaskPlanViewState} TaskPlanViewState */
/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("./taskCreateContracts").TaskSystemStatus} TaskSystemStatus */
/** @typedef {import("../task-planning/taskPlanContracts").TaskPlanCounts} TaskPlanCounts */
/** @typedef {TaskPlanViewState & {planCounts: TaskPlanCounts, preflightStatus: TaskPreflightState["status"], scopeConfirmed: boolean, submitError: string, submitting: boolean, system: TaskSystemStatus | null, unresolvedPolicy: string}} TaskLaunchState */

/** @param {TaskLaunchState} state */
export function taskLaunchCopy({
  blocked,
  categoryCompletionRequired,
  countMismatch,
  noExecutable,
  partialPlan,
  planCounts,
  preflightStatus,
  requiresScopeConfirmation,
  scopeConfirmed,
  submitError,
  submitting,
  system,
  unresolvedPolicy,
}) {
  const submitLabel = taskSubmitLabel({
    blocked,
    categoryCompletionRequired,
    countMismatch,
    noExecutable,
    partialPlan,
    planCounts,
    unresolvedPolicy,
  });
  const launchStatus = taskLaunchStatus({
    blocked,
    categoryCompletionRequired,
    countMismatch,
    noExecutable,
    preflightStatus,
    requiresScopeConfirmation,
    scopeConfirmed,
    submitError,
    submitting,
    system,
    unresolvedPolicy,
  });
  return { launchStatus, submitLabel };
}

/** @param {Pick<TaskLaunchState, "blocked" | "categoryCompletionRequired" | "countMismatch" | "noExecutable" | "partialPlan" | "planCounts" | "unresolvedPolicy">} state */
function taskSubmitLabel(state) {
  if (state.categoryCompletionRequired) return "请先补齐商品品类";
  if (state.countMismatch) return "评论数量需要重新预检";
  if (state.noExecutable) return "没有可执行评论";
  if (state.blocked) {
    if (state.unresolvedPolicy === "run_ready") {
      return `启动 ${state.planCounts.executable.toLocaleString()} 组已就绪评论`;
    }
    return state.unresolvedPolicy === "block_all"
      ? "保存任务，等待问题处理"
      : "选择处理方式后继续";
  }
  return state.partialPlan
    ? `启动 ${state.planCounts.executable.toLocaleString()} 组可执行评论`
    : "开始分析";
}

/** @param {Pick<TaskLaunchState, "submitting" | "submitError" | "preflightStatus">} state */
function pendingLaunchStatus(state) {
  if (state.submitting) return "正在创建任务，请稍候…";
  if (state.submitError) return "配置已保留，可以重试创建。";
  if (state.preflightStatus === "loading" || state.preflightStatus === "idle") {
    return "正在检查数据，不会调用模型…";
  }
  if (state.preflightStatus === "error") {
    return "检查未完成，请在上方重新检查数据。";
  }
  return "";
}

/** @param {Pick<TaskLaunchState, "categoryCompletionRequired" | "countMismatch" | "noExecutable" | "blocked" | "unresolvedPolicy" | "requiresScopeConfirmation" | "scopeConfirmed">} state */
function planLaunchStatus(state) {
  if (state.categoryCompletionRequired) return "请先补齐上方提示的商品品类。";
  if (state.countMismatch) return "评论数量校验未通过，请重新检查数据。";
  if (state.noExecutable) return "当前范围没有可执行评论，请修改分析数据。";
  if (state.blocked && !state.unresolvedPolicy) {
    return "请在上方选择未解决问题的处理方式。";
  }
  if (state.blocked && state.unresolvedPolicy === "block_all") {
    return "仅保存任务，处理完数据问题后再开始分析。";
  }
  if (state.requiresScopeConfirmation && !state.scopeConfirmed) {
    return "请先确认上方的分析范围与排除项。";
  }
  return "";
}

/** @param {Pick<TaskLaunchState, "blocked" | "categoryCompletionRequired" | "countMismatch" | "noExecutable" | "preflightStatus" | "requiresScopeConfirmation" | "scopeConfirmed" | "submitError" | "submitting" | "system" | "unresolvedPolicy">} state */
function taskLaunchStatus(state) {
  const pendingStatus = pendingLaunchStatus(state);
  if (pendingStatus) return pendingStatus;
  const planStatus = planLaunchStatus(state);
  if (planStatus) return planStatus;
  if ((state.system?.my_running_tasks ?? 0) >= 3) {
    return "并行名额已满，启动后将进入队列。";
  }
  return "确认任务名称与模型后，即可开始分析。";
}
