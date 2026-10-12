import { useProtectedData } from "../../hooks/useProtectedData";
import { useDataRefresh } from "../../hooks/useDataRefresh";
import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "../../api";
import {
  refreshProductState,
  refreshServerState,
  serverStateKeys,
} from "../../shared/serverState";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").UploadDialog} UploadDialog */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */

/** @param {Pick<ProductMasterProps,"focus"|"routeDetailTab">} props */
export function useProductMasterState({ focus, routeDetailTab = "" }) {
  const { mutate: mutateCache } = useSWRConfig();
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [dialog, setDialog] = useState(/** @type {UploadDialog | null} */ (null));
  const [protectedOperation, setProtectedOperation] = useState(false);
  const [detailTab, setDetailTab] = useState("rows");

  const {
    data: datasets = [],
    error: datasetsError,
    isLoading: datasetsLoading,
    mutate: mutateDatasets,
  } = useSWR(
    serverStateKeys.productDatasets,
    () => api.datasets("products"),
    MANAGED_REFRESH_OPTIONS,
  );
  const detailInclude = detailTab === "impact" ? "audit" : "";
  const {
    data: fetchedSelected = null,
    error: detailError,
    isLoading: detailLoading,
    mutate: mutateSelected,
  } = useSWR(
    selectedId ? serverStateKeys.productDataset(selectedId, detailInclude) : null,
    () => {
      if (!selectedId) return null;
      return api.dataset(selectedId, { include: detailInclude });
    },
    MANAGED_REFRESH_OPTIONS,
  );
  useDataRefresh(() => mutateDatasets(), { loading: datasetsLoading });
  useDataRefresh(() => mutateSelected(), {
    enabled: Boolean(selectedId),
    loading: detailLoading,
    identity: `${selectedId}:${detailInclude}`,
  });
  const selected = useProtectedData(
    fetchedSelected,
    protectedOperation || Boolean(dialog),
    selectedId || "",
  );
  const focusedId = focus?.datasetKind === "products" ? focus.id : undefined;
  useEffect(() => {
    setSelectedId(
      (current) =>
        focusedId ??
        ((protectedOperation || dialog) && current
          ? current
          : datasets.some((item) => item.id === current)
            ? current
            : (datasets[0]?.id ?? null)),
    );
  }, [datasets, focusedId, protectedOperation, dialog]);
  useEffect(() => {
    if (["rows", "impact"].includes(routeDetailTab)) {
      setDetailTab(routeDetailTab);
    } else if (["audit", "references"].includes(routeDetailTab)) {
      setDetailTab("impact");
    } else {
      setDetailTab("rows");
    }
  }, [routeDetailTab, focusedId]);
  const { dimensionAudit, currentVersionId } = productMasterSelection(selected);
  const loadState = productMasterLoadState({
    datasetsLoading,
    datasets,
    selectedId,
    detailLoading,
    datasetsError,
    detailError,
  });
  return {
    ...loadState,
    // 各读取状态保留错误与旧数据；统一重试不再重复显示父级和列表的同一告警。
    retry: () =>
      refreshServerState(mutateCache, ["data-assets"]).catch(() => undefined),
    selectedId,
    setProtectedOperation,
    setSelectedId,
    dialog,
    setDialog,
    detailTab,
    setDetailTab,
    datasets,
    mutateDatasets,
    selected,
    mutateSelected,
    /** @param {DatasetRecord} [dataset] */
    onProductChanged: async (dataset) => {
      await Promise.all([
        dataset ? mutateSelected(dataset, false) : mutateSelected(),
        refreshProductState(mutateCache),
      ]);
    },
    dimensionAudit,
    currentVersionId,
  };
}

/** @param {{datasetsLoading: boolean, datasets: DatasetRecord[], selectedId: string | null, detailLoading: boolean, datasetsError: unknown, detailError: unknown}} state */
function productMasterLoadState({
  datasetsLoading,
  datasets,
  selectedId,
  detailLoading,
  datasetsError,
  detailError,
}) {
  return {
    loading: Boolean(
      datasetsLoading ||
      (datasets.length && !selectedId) ||
      (selectedId && detailLoading),
    ),
    error: datasetsError ?? detailError,
  };
}

/** @param {DatasetRecord | null} selected */
function productMasterSelection(selected) {
  const dimensionAudit =
    selected?.audit?.filter((entry) =>
      [
        "product_update",
        "dimension_row_update",
        "dimension_category_completion",
      ].includes(entry.action),
    ) ?? [];
  const currentVersionId = selected?.version_id;
  return { dimensionAudit, currentVersionId };
}
