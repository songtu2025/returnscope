import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { api } from "../../api";
import { refreshProductState, serverStateKeys } from "../../shared/serverState";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").UploadDialog} UploadDialog */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */

/** @param {Pick<ProductMasterProps,"notify"|"focus"|"routeDetailTab">} props */
export function useProductMasterState({ notify, focus, routeDetailTab = "" }) {
  const { mutate: mutateCache } = useSWRConfig();
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [dialog, setDialog] = useState(/** @type {UploadDialog | null} */ (null));
  const [detailTab, setDetailTab] = useState("rows");

  const {
    data: datasets = [],
    error: datasetsError,
    isLoading: datasetsLoading,
    mutate: mutateDatasets,
  } = useSWR(serverStateKeys.productDatasets, () => api.datasets("products"));
  const detailInclude = detailTab === "impact" ? "audit" : "";
  const {
    data: selected = null,
    error: detailError,
    isLoading: detailLoading,
    mutate: mutateSelected,
  } = useSWR(
    selectedId ? serverStateKeys.productDataset(selectedId, detailInclude) : null,
    () => {
      if (!selectedId) return null;
      return api.dataset(selectedId, { include: detailInclude });
    },
  );
  const focusedId = focus?.datasetKind === "products" ? focus.id : undefined;
  useEffect(() => {
    setSelectedId(
      (current) =>
        focusedId ??
        (datasets.some((item) => item.id === current)
          ? current
          : (datasets[0]?.id ?? null)),
    );
  }, [datasets, focusedId]);
  useEffect(() => {
    if (["rows", "impact"].includes(routeDetailTab)) {
      setDetailTab(routeDetailTab);
    } else if (["audit", "references"].includes(routeDetailTab)) {
      setDetailTab("impact");
    } else {
      setDetailTab("rows");
    }
  }, [routeDetailTab, focusedId]);
  useEffect(() => {
    if (!datasetsError) return;
    notify(
      datasetsError instanceof Error ? datasetsError.message : "产品信息读取失败",
      "error",
    );
  }, [datasetsError, notify]);
  useEffect(() => {
    if (!detailError) return;
    notify(
      detailError instanceof Error ? detailError.message : "产品详情读取失败",
      "error",
    );
  }, [detailError, notify]);
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
    retry: () =>
      datasetsError
        ? mutateDatasets((current) => current, {
            revalidate: true,
            throwOnError: false,
          })
        : mutateSelected((current) => current, {
            revalidate: true,
            throwOnError: false,
          }),
    selectedId,
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
