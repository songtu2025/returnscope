import { useCallback, useEffect, useMemo, useState } from "react";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
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
export function useClassificationStandardList(notify) {
  const [standards, setStandards] = useState(
    /** @type {ClassificationStandardSummary[]} */ ([]),
  );
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(
    /** @type {"all" | "active" | "inactive"} */ ("all"),
  );
  const [loading, setLoading] = useState(true);
  const loadStandards = useCallback(async () => {
    const values = await classificationStandardApi.classificationStandards();
    setStandards(values);
    return values;
  }, []);

  useEffect(() => {
    loadStandards()
      .catch((error) => notify(errorMessage(error), "error"))
      .finally(() => setLoading(false));
  }, [loadStandards, notify]);

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
    loadStandards,
    filteredStandards,
    totals,
  };
}
