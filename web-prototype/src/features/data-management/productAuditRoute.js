import { buildHash, parseHash } from "../../app/hashRouter";
import { productReferenceReturnQuery } from "./productReferenceRoute";

/** @param {import("../../app/navigation").AppRoute | null} target */
export function productAuditReturnQuery(target) {
  const query = productReferenceReturnQuery(target);
  if (!query) return null;
  return {
    ...query,
    ...(target?.query.result_return
      ? { result_return: target.query.result_return }
      : {}),
  };
}

/** @param {unknown} msku @param {unknown} store @param {import("../../app/navigation").AppRoute} [source] */
export function productAuditQuery(msku, store, source = parseHash()) {
  const returnQuery = productAuditReturnQuery(source);
  if (
    !returnQuery ||
    typeof msku !== "string" ||
    !msku ||
    typeof store !== "string" ||
    !store
  )
    return null;
  return {
    ...returnQuery,
    tab: "rows",
    rows_q: msku,
    rows_store: store,
    rows_category: "",
    rows_page: 1,
    audit_return: buildHash("data-assets", returnQuery),
  };
}
