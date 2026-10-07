import { api } from "../../api";
import { errorStatus } from "../../shared/api/requestErrors";
import { serverStateKeys } from "../../shared/serverState";

/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("./taskCreateContracts").TaskPlanViewState} TaskPlanViewState */
/** @typedef {import("../task-planning/taskPlanContracts").TaskExecutionPlan} TaskExecutionPlan */
/**
 * @typedef {{submitting: boolean, preflight: TaskPreflightState, unresolvedPolicy: string, planState: TaskPlanViewState, scopeConfirmed: boolean, form: TaskForm, segmentOrder: string[], mutateServerState: ReturnType<typeof import("swr").useSWRConfig>["mutate"], setSubmitting: (value: boolean) => void, setSubmitError: (value: string) => void, setPrepared: (value: boolean) => void, setPreflight: (value: TaskPreflightState) => void, setUnresolvedPolicy: (value: string) => void, notify: (message: string, type?: "success" | "error") => void, onDraftComplete?: () => void, onChanged: () => void | Promise<unknown>, onNavigate: import("../../app/navigation").Navigate}} TaskSubmission
 */
/** @typedef {TaskSubmission & {preflight: TaskPreflightState & {data: TaskExecutionPlan}}} ReadyTaskSubmission */

/** @param {TaskSubmission} submission */
export async function submitNewTask(submission) {
  if (!canSubmitTask(submission)) return;
  const {
    setSubmitting,
    setSubmitError,
    notify,
    onDraftComplete,
    onChanged,
    onNavigate,
  } = submission;
  setSubmitting(true);
  setSubmitError("");
  try {
    await createPreparedTask(submission);
    notify("任务已创建，后台执行器会自动领取");
    onDraftComplete?.();
    onChanged();
    onNavigate("tasks");
  } catch (error) {
    handleTaskCreationFailure(error, submission);
  } finally {
    setSubmitting(false);
  }
}

/** @param {TaskSubmission} submission @returns {submission is ReadyTaskSubmission} */
function canSubmitTask(submission) {
  const { submitting, preflight, unresolvedPolicy, planState, scopeConfirmed } =
    submission;
  return !(
    submitting ||
    preflight.status !== "ready" ||
    !preflight.data ||
    !unresolvedPolicy ||
    planState.categoryCompletionRequired ||
    planState.countMismatch ||
    planState.noExecutable ||
    (planState.requiresScopeConfirmation && !scopeConfirmed)
  );
}

/** @param {ReadyTaskSubmission} submission */
async function createPreparedTask({
  form,
  preflight,
  unresolvedPolicy,
  segmentOrder,
  mutateServerState,
}) {
  await api.createTask({
    ...form,
    store: null,
    listing: null,
    title: form.title.trim(),
    plan_hash: preflight.data.plan_hash,
    unresolved_policy: unresolvedPolicy,
    segment_order: segmentOrder,
  });
  try {
    await mutateServerState(
      serverStateKeys.taskList,
      api.tasks({ include_archived: true }),
      { revalidate: false },
    );
  } catch {
    await mutateServerState(serverStateKeys.taskList, undefined, {
      revalidate: false,
    });
  }
}

/** @param {unknown} error @param {TaskSubmission} submission */
function handleTaskCreationFailure(
  error,
  { setPrepared, setPreflight, setUnresolvedPolicy, setSubmitError, notify },
) {
  const status = errorStatus(error);
  const message = error instanceof Error ? error.message : "暂时无法创建任务，请重试。";
  if (status === 409) {
    setPrepared(true);
    setPreflight({
      status: "error",
      data: null,
      error: "执行计划已变化，请重新预检后再启动任务。",
    });
    setUnresolvedPolicy("");
  } else {
    setSubmitError(message);
  }
  notify(message, "error");
}
