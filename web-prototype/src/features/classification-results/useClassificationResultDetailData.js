import { useEffect, useMemo, useState } from "react";

import { api } from "../../api";

export function useClassificationResultDetailData({ route, notify }) {
  const [result, setResult] = useState(null);
  const [summary, setSummary] = useState(null);
  const [records, setRecords] = useState(null);
  const [drilldowns, setDrilldowns] = useState({
    problem: [],
    product_name: [],
    product_sku: [],
  });
  const [loading, setLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [error, setError] = useState("");

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
        if (active && loadError.name !== "AbortError") setError(loadError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [route.version]);

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
        if (active && loadError.name !== "AbortError") {
          notify(loadError.message, "error");
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
  };
}
