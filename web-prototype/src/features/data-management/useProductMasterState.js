import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "../../api";
import { serverStateKeys } from "../../shared/serverState";

/** @typedef {import("./productMasterContracts").DatasetRecord} DatasetRecord */
/** @typedef {import("./productMasterContracts").UploadDialog} UploadDialog */
/** @typedef {import("./productMasterContracts").ProductMasterProps} ProductMasterProps */

/** @param {Pick<ProductMasterProps,"notify"|"focus"|"routeDetailTab">} props */
export function useProductMasterState({ notify, focus, routeDetailTab = "" }) {
  const [selectedId, setSelectedId] = useState(/** @type {string | null} */ (null));
  const [dialog, setDialog] = useState(/** @type {UploadDialog | null} */ (null));
  const [detailTab, setDetailTab] = useState("rows");

  const {
    data: datasets = [],
    error: datasetsError,
    mutate: mutateDatasets,
  } = useSWR(serverStateKeys.productDatasets, () => api.datasets("products"));
  const detailInclude = detailTab === "impact" ? "versions,audit" : "versions";
  const {
    data: selected = null,
    error: detailError,
    mutate: mutateSelected,
  } = useSWR(
    selectedId ? serverStateKeys.productDataset(selectedId, detailInclude) : null,
    () => {
      if (!selectedId) return null;
      return api.dataset(selectedId, { include: detailInclude });
    },
    { keepPreviousData: true },
  );

  useEffect(() => {
    setSelectedId((current) =>
      datasets.some((item) => item.id === current)
        ? current
        : (datasets[0]?.id ?? null),
    );
  }, [datasets]);
  useEffect(() => {
    if (["rows", "versions", "impact"].includes(routeDetailTab)) {
      setDetailTab(routeDetailTab);
    } else if (["audit", "references"].includes(routeDetailTab)) {
      setDetailTab("impact");
    }
  }, [routeDetailTab]);
  useEffect(() => {
    if (!datasetsError) return;
    notify(
      datasetsError instanceof Error ? datasetsError.message : "商品数据读取失败",
      "error",
    );
  }, [datasetsError, notify]);
  useEffect(() => {
    if (!detailError) return;
    notify(
      detailError instanceof Error ? detailError.message : "商品详情读取失败",
      "error",
    );
  }, [detailError, notify]);
  useEffect(() => {
    if (!focus || focus.datasetKind !== "products") return;
    setSelectedId(focus.id ?? null);
    setDetailTab("rows");
  }, [focus]);

  const { dimensionAudit, currentVersionId } = productMasterSelection(selected);
  return {
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
    dimensionAudit,
    currentVersionId,
  };
}

/** @param {DatasetRecord | null} selected */
function productMasterSelection(selected) {
  const dimensionAudit =
    selected?.audit?.filter((entry) =>
      ["dimension_row_update", "dimension_category_completion"].includes(entry.action),
    ) ?? [];
  const currentVersionId = selected?.versions?.find(
    (version) => version.version === selected.current_version,
  )?.id;
  return { dimensionAudit, currentVersionId };
}
