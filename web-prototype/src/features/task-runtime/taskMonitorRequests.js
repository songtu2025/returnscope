import { api } from "../../api";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskPayload} TaskPayload */
/** @typedef {import("./taskRuntimeContracts").SegmentAction} SegmentAction */

/**
 * 当前组件使用的任务 API 响应契约。静态类型集中在消费边界，不改变请求行为。
 * @type {{
 *   tasks: (filters?: Record<string, string | number | boolean | null | undefined>, options?: RequestInit) => Promise<AnalysisTask[]>,
 *   task: (id: string, options?: RequestInit) => Promise<AnalysisTask>,
 *   archiveTasks: (taskIds: string[], archived: boolean) => Promise<unknown>,
 *   eventUrl: (taskId: string, after?: number) => string,
 *   renameTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   cancelTask: (id: string, payload: TaskPayload) => Promise<unknown>,
 *   pauseTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   resumeTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   retryTask: (id: string) => Promise<AnalysisTask>,
 *   retryTaskSegment: (id: string, segmentKey: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   retrySegmentResultPublish: (id: string, segmentId: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   controlTaskSegment: (id: string, segmentKey: string, action: SegmentAction, payload: TaskPayload) => Promise<AnalysisTask>,
 *   setTaskParallelism: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   reorderTaskSegments: (id: string, payload: TaskPayload) => Promise<AnalysisTask>,
 *   preflightTaskReplan: (id: string, payload: TaskPayload) => Promise<import("../task-planning/taskPlanContracts").TaskExecutionPlan>,
 *   replanTask: (id: string, payload: TaskPayload) => Promise<AnalysisTask>
 * }}
 */
export const taskMonitorApi = api;
/** @param {unknown} error */
export function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/** @param {unknown} error */
export function errorStatus(error) {
  return typeof error === "object" && error !== null && "status" in error
    ? error.status
    : undefined;
}
