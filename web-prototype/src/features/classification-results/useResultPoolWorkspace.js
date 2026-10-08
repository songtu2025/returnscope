import { useResultSelection } from "./useResultSelection";
import { useEffect, useMemo, useState } from "react";
import { useClassificationResultListData } from "./useClassificationResultListData";

/** @typedef {import("./classificationResultListContracts").ClassificationResultListProps} ClassificationResultListProps */

/** @param {import("./classificationResultListContracts").ClassificationResultListProps} props */
export function useResultPoolWorkspace({ route, updateRoute, userId }) {
  const [filters, setFilters] = useState({
    q: route.q,
    storeSite: route.storeSite,
    listing: route.listing,
    qualityStatus: route.qualityStatus,
  });
  const selection = useResultSelection({ route, updateRoute, userId });
  useEffect(() => {
    setFilters({
      q: route.q,
      storeSite: route.storeSite,
      listing: route.listing,
      qualityStatus: route.qualityStatus,
    });
  }, [route.listing, route.q, route.qualityStatus, route.storeSite]);

  const query = useMemo(
    () => ({
      page: route.page,
      page_size: route.pageSize,
      q: route.q,
      store_site: route.storeSite,
      listing: route.listing,
      quality_status: route.qualityStatus,
    }),
    [
      route.listing,
      route.page,
      route.pageSize,
      route.q,
      route.qualityStatus,
      route.storeSite,
    ],
  );

  const { data, loading, error, hasNewResults, load } =
    useClassificationResultListData(query);

  const activeFilters = Boolean(
    route.q || route.storeSite || route.listing || route.qualityStatus,
  );
  const totalPages = Math.max(Math.ceil((data?.total ?? 0) / route.pageSize), 1);

  /** @param {number} page */
  const changePage = (page) => updateRoute({ page });
  /** @param {number} pageSize */
  const changePageSize = (pageSize) => updateRoute({ page: 1, pageSize });

  return {
    filters,
    setFilters,
    ...selection,
    data,
    loading,
    error,
    hasNewResults,
    load,
    activeFilters,
    totalPages,
    changePage,
    changePageSize,
  };
}
