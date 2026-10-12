import { useDataRefresh } from "../../hooks/useDataRefresh";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { errorStatus } from "../../shared/api/requestErrors";
import { classificationDraftErrorMessage as errorMessage } from "./classificationDraftSelection";
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSummary} ClassificationStandardSummary */
/** @param {ClassificationStandardSummary[]} standards @param {string} query @param {"all" | "active" | "inactive"} statusFilter */
function filterClassificationStandards(standards, query, statusFilter) {
  const keyword = query.trim().toLowerCase();
  return standards.filter((standard) => {
    const matchesStatus = statusFilter === "all" || standard.status === statusFilter;
    const text =
      `${standard.name} ${standard.product_context} ${standard.agent_family}`.toLowerCase();
    return matchesStatus && (!keyword || text.includes(keyword));
  });
}
/** @param {ClassificationStandardSummary[]} standards */
function classificationStandardTotals(standards) {
  return {
    active: standards.filter((item) => item.status === "active").length,
    categories: standards
      .filter((item) => item.status === "active")
      .reduce((sum, item) => sum + item.category_count, 0),
    labels: standards
      .filter((item) => item.status === "active")
      .reduce((sum, item) => sum + item.label_count, 0),
  };
}
/** @param {(message: string, tone?: string) => void} notify */
export function useClassificationStandardList(notify, enabled = true) {
  const [standards, setStandards] = useState(
    /** @type {ClassificationStandardSummary[]} */ ([]),
  );
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(
    /** @type {"all" | "active" | "inactive"} */ ("all"),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [hasData, setHasData] = useState(false);
  const generationRef = useRef(0);
  const loadStandards = useCallback(async (background = false) => {
    const generation = ++generationRef.current;
    if (!background) setLoading(true);
    setError("");
    try {
      const values = await classificationStandardApi.classificationStandards();
      if (generation !== generationRef.current) return values;
      setStandards(values);
      setHasData(true);
      return values;
    } catch (failure) {
      if (generation !== generationRef.current) return [];
      setError(errorMessage(failure));
      if ([401, 403].includes(Number(errorStatus(failure)))) {
        setStandards([]);
        setHasData(false);
      }
      throw failure;
    } finally {
      if (generation === generationRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStandards().catch((error) => notify(errorMessage(error), "error"));
    return () => {
      generationRef.current += 1;
    };
  }, [loadStandards, notify]);

  useDataRefresh(() => loadStandards(true), {
    enabled,
    loading,
    domains: ["classification-standards"],
  });
  const filteredStandards = useMemo(
    () => filterClassificationStandards(standards, query, statusFilter),
    [query, standards, statusFilter],
  );
  const totals = useMemo(() => classificationStandardTotals(standards), [standards]);
  return {
    query,
    setQuery,
    statusFilter,
    setStatusFilter,
    loading,
    error,
    hasData,
    loadStandards,
    filteredStandards,
    totals,
  };
}
