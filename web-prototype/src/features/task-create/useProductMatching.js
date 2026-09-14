import { useState } from "react";

import { api } from "../../api";
import { primaryPlanStore } from "./newTaskPolicy";

export function useProductMatching({
  dataEntryMode,
  form,
  invalidatePreflight,
  mysqlDraft,
  notify,
  onDraftChange,
  onNavigate,
  preflight,
  products,
  selectedDataLabel,
  selectedProducts,
  selectedReturns,
  setForm,
  setSubmitting,
  setVersions,
}) {
  const [matchingOpen, setMatchingOpen] = useState(false);

  const resolveCategories = () => {
    const unresolvedProducts = preflight.data?.unresolved_products ?? [];
    if (
      unresolvedProducts.length > 0 &&
      unresolvedProducts.some((item) => item.editable && item.store)
    ) {
      setMatchingOpen(true);
      return;
    }
    const productVersion = products.find(
      (item) => item.version_id === form.product_version_id,
    );
    onDraftChange?.({
      form,
      step: 2,
      resumePreflight: true,
      dataEntryMode,
      selectedDataLabel,
      mysqlDraft,
    });
    onNavigate("data", {
      kind: "dataset",
      id: productVersion?.dataset_id,
      datasetKind: "products",
      returnToTask: true,
      taskTitle: form.title.trim() || "待创建分析任务",
      store: primaryPlanStore(preflight.data),
      unresolvedProducts: preflight.data?.unresolved_products ?? [],
      categoryOptions: preflight.data?.category_options ?? [],
      blockedCommentCount:
        preflight.data?.unresolved_product_comment_count ??
        preflight.data?.blocked_count ??
        0,
    });
  };

  const saveProductMatches = async (items) => {
    if (!selectedProducts?.dataset_id) return;
    setSubmitting(true);
    try {
      const updated = await api.completeProductCategories(selectedProducts.dataset_id, {
        expected_version: selectedProducts.version,
        store: primaryPlanStore(preflight.data),
        items,
        change_note: `确认任务“${
          form.title || selectedReturns?.dataset_name || "退货明细"
        }”的商品关联`,
      });
      const latestVersion = updated.versions?.find(
        (version) => version.version === updated.current_version,
      );
      if (!latestVersion?.id) {
        throw new Error("产品信息已更新，但未返回最新版本，请刷新后重试");
      }
      setVersions(await api.dataVersions());
      setMatchingOpen(false);
      invalidatePreflight();
      setForm((current) => ({ ...current, product_version_id: latestVersion.id }));
      notify(`已保存 ${items.length.toLocaleString()} 个商品关联，正在重新生成计划`);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setSubmitting(false);
    }
  };

  return { matchingOpen, resolveCategories, saveProductMatches, setMatchingOpen };
}
