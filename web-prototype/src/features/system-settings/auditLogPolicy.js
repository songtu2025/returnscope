import { navigateHash } from "../../app/hashRouter";

const PAGE_SIZE = 20;
export { PAGE_SIZE };
/** @typedef {{query: Partial<AuditFilters> & {page?: string | number}}} AuditRoute */
/** @typedef {{actor_id: string, entity_type: string, entity_id: string, action: string, date_from: string, date_to: string}} AuditFilters */

/** @param {unknown} value @param {number} [fallback] */
export function numberParam(value, fallback = 1) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

/** @param {AuditRoute} route @param {Record<string, string | number>} changes */
export function writeAuditRoute(route, changes) {
  navigateHash("settings", {
    tab: "audit",
    actor_id: route.query.actor_id || "",
    entity_type: route.query.entity_type || "",
    entity_id: route.query.entity_id || "",
    action: route.query.action || "",
    date_from: route.query.date_from || "",
    date_to: route.query.date_to || "",
    page: numberParam(route.query.page) > 1 ? route.query.page : "",
    ...changes,
  });
}

/** @param {AuditRoute} route @returns {AuditFilters} */
export function filtersFromRoute(route) {
  return {
    actor_id: route.query.actor_id || "",
    entity_type: route.query.entity_type || "",
    entity_id: route.query.entity_id || "",
    action: route.query.action || "",
    date_from: route.query.date_from || "",
    date_to: route.query.date_to || "",
  };
}

/** @param {Pick<AuditFilters, "date_from" | "date_to">} filters */
export function getDateRangeError(filters) {
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) {
    return "结束日期不能早于开始日期。";
  }
  return "";
}
