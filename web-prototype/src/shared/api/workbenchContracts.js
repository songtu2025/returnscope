/**
 * @typedef {{
 *   route?: string,
 *   task_id?: string,
 *   segment_id?: string,
 *   result_version_id?: string,
 *   action?: string,
 *   dashboard_id?: string,
 *   version_id?: string,
 *   report_id?: string,
 *   tab?: string,
 * }} WorkbenchTarget
 *
 * @typedef {{id?: string | null, name?: string | null}} WorkbenchActor
 *
 * @typedef {{
 *   type: string,
 *   object_type: string,
 *   object_id: string,
 *   title: string,
 *   reason?: string | null,
 *   status?: string | null,
 *   actor?: WorkbenchActor | null,
 *   updated_at?: string | null,
 *   target: WorkbenchTarget,
 * }} WorkbenchAction
 *
 * @typedef {{
 *   type: string,
 *   object_id: string,
 *   version_id: string,
 *   version_no: number,
 *   title: string,
 *   status: string,
 *   updated_at?: string | null,
 *   target: WorkbenchTarget,
 * }} WorkbenchOutput
 *
 * @typedef {{
 *   actions: WorkbenchAction[],
 *   recent_outputs: WorkbenchOutput[],
 *   counts: Record<string, number>,
 * }} WorkbenchSummary
 */

export {};
