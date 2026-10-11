import { useState } from "react";
import { useSWRConfig } from "swr";
import { api } from "../../api";
import { refreshProductState } from "../../shared/serverState";
import { primaryPlanStore } from "./newTaskPolicy";

/** @typedef {import("./taskCreateContracts").DataVersion} DataVersion */
/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("./taskCreateContracts").TaskForm} TaskForm */
/** @typedef {import("./taskCreateContracts").TaskPreflightState} TaskPreflightState */
/** @typedef {import("./mysqlReturnContracts").MysqlReturnFormState} MysqlReturnFormState */
/** @typedef {import("./productMatchPolicy").ProductMatchDraft} ProductMatchDraft */

/**
 * @param {{dataEntryMode: "upload" | "mysql", form: TaskForm, invalidatePreflight: () => void, mysqlDraft?: Partial<MysqlReturnFormState>, notify: (message: string, type?: "success" | "error") => void, onDraftChange?: (draft: TaskDraft) => void, onNavigate: import("../../app/navigation").Navigate, preflight: TaskPreflightState, products: DataVersion[], selectedDataLabel: string, selectedProducts?: DataVersion, selectedReturns?: DataVersion, setForm: import("react").Dispatch<import("react").SetStateAction<TaskForm>>, setSubmitting: import("react").Dispatch<import("react").SetStateAction<boolean>>, setVersions: import("react").Dispatch<import("react").SetStateAction<DataVersion[]>>}} options
 */

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
  const { mutate } = useSWRConfig();
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

  /** @param {ProductMatchDraft[]} items */
  const saveProductMatches = async (items) => {
    if (!selectedProducts?.dataset_id) return;
    setSubmitting(true);
    try {
      const updated =
        /** @type {{version_id?: string, versions?: {id: string, version: number}[], current_version: number}} */ (
          await api.completeProductCategories(selectedProducts.dataset_id, {
            expected_version: selectedProducts.version,
            store: primaryPlanStore(preflight.data),
            items,
            change_note: `确认任务“${
              form.title || selectedReturns?.dataset_name || "用户反馈数据"
            }”的商品关联`,
          })
        );
      const latestId =
        updated.version_id ??
        updated.versions?.find((version) => version.version === updated.current_version)
          ?.id;
      if (!latestId) {
        throw new Error("产品信息已更新，请刷新后重试");
      }
      setVersions(await api.dataVersions());
      await refreshProductState(mutate);
      setMatchingOpen(false);
      invalidatePreflight();
      setForm((current) => ({ ...current, product_version_id: latestId }));
      notify(`已保存 ${items.length.toLocaleString()} 个商品关联，正在重新生成计划`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "保存商品关联失败", "error");
    } finally {
      setSubmitting(false);
    }
  };

  return { matchingOpen, resolveCategories, saveProductMatches, setMatchingOpen };
}
