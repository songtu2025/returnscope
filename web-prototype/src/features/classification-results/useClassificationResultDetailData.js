import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../../api";

/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */

/**
 * @param {{ route: ClassificationResultRoute, notify: (message: string, type: "error") => void }} options
 */
export function useClassificationResultDetailData({ route, notify }) {
  const [result, setResult] = useState(
    /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse | null} */ (
      null
    ),
  );
  const [summary, setSummary] = useState(
    /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultSummaryResponse | null} */ (
      null
    ),
  );
  const [records, setRecords] = useState(
    /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultRecordsResponse | null} */ (
      null
    ),
  );
  const [drilldowns, setDrilldowns] = useState({
    problem:
      /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultDrilldownItemResponse[]} */ ([]),
    product_name:
      /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultDrilldownItemResponse[]} */ ([]),
    product_sku:
      /** @type {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultDrilldownItemResponse[]} */ ([]),
  });
  const [loading, setLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadRevision, setReloadRevision] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    Promise.all([
      api.classificationResult(route.version, { signal: controller.signal }),
      api.classificationResultSummary(route.version, { signal: controller.signal }),
    ])
      .then(([version, versionSummary]) => {
        if (!active) return;
        setResult(version);
        setSummary(versionSummary);
      })
      .catch((loadError) => {
        if (
          active &&
          (!(loadError instanceof Error) || loadError.name !== "AbortError")
        ) {
          setError(loadError instanceof Error ? loadError.message : "请求失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [reloadRevision, route.version]);

  const retry = useCallback(() => setReloadRevision((current) => current + 1), []);

  const detailQuery = useMemo(
    () => ({
      page: route.recordPage,
      page_size: route.pageSize,
      problem: route.problem,
      product_name: route.productName,
      product_sku: route.productSku,
      order_id: route.orderId,
    }),
    [
      route.orderId,
      route.pageSize,
      route.problem,
      route.productName,
      route.productSku,
      route.recordPage,
    ],
  );

  useEffect(() => {
    if (route.tab === "history") {
      setRecordsLoading(false);
      return undefined;
    }
    let active = true;
    const controller = new AbortController();
    setRecordsLoading(true);
    Promise.all([
      api.classificationResultRecords(route.version, detailQuery, {
        signal: controller.signal,
      }),
      api.classificationResultDrilldown(
        route.version,
        "problem",
        { page: 1, page_size: 100 },
        { signal: controller.signal },
      ),
      api.classificationResultDrilldown(
        route.version,
        "product_name",
        { page: 1, page_size: 100, problem: route.problem },
        { signal: controller.signal },
      ),
      api.classificationResultDrilldown(
        route.version,
        "product_sku",
        {
          page: 1,
          page_size: 100,
          problem: route.problem,
          product_name: route.productName,
        },
        { signal: controller.signal },
      ),
    ])
      .then(([recordPage, problems, names, skus]) => {
        if (!active) return;
        setRecords(recordPage);
        setDrilldowns({
          problem: problems.items ?? [],
          product_name: names.items ?? [],
          product_sku: skus.items ?? [],
        });
      })
      .catch((loadError) => {
        if (
          active &&
          (!(loadError instanceof Error) || loadError.name !== "AbortError")
        ) {
          notify(loadError instanceof Error ? loadError.message : "请求失败", "error");
        }
      })
      .finally(() => {
        if (active) setRecordsLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [detailQuery, notify, route.productName, route.problem, route.tab, route.version]);

  return {
    result,
    summary,
    records,
    drilldowns,
    loading,
    recordsLoading,
    error,
    retry,
  };
}
