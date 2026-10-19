/** @param {import("../../app/navigation").AppRoute | null} target */
export function productReferenceReturnQuery(target) {
  if (
    target?.page !== "data-assets" ||
    target.query.tab !== "impact" ||
    (target.query.view && target.query.view !== "products")
  )
    return null;
  const fields = [
    "view",
    "dataset",
    "tab",
    "rows_q",
    "rows_store",
    "rows_category",
    "rows_page",
    "rows_page_size",
    "reference_page",
  ];
  return {
    ...Object.fromEntries(
      fields
        .filter((key) => target.query[key] !== undefined)
        .map((key) => [key, target.query[key]]),
    ),
    ...(target.query.return_to === "task-create" ? { return_to: "task-create" } : {}),
  };
}
