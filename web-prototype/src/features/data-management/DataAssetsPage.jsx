import { useEffect, useMemo } from "react";
import "../../styles/operations.css";
import "../../styles/product-info.css";
import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { ProductMasterWorkspace } from "./ProductMasterWorkspace";
import { readTaskDraft, updateTaskDraft } from "../task-create/taskDraftStorage";
import { ImportRulesPage } from "./ImportRulesPage";

/** @typedef {import("./productMasterContracts").Navigate} Navigate */
/** @typedef {import("./productMasterContracts").TaskRepairContext} TaskRepairContext */
/** @typedef {{query: {view?: string, dataset?: string, return_to?: string, tab?: string, reference_version?: string, reference_page?: string | number}}} DataAssetsRoute */

/**
 * @param {{route: DataAssetsRoute, notify: (message: string, tone?: string) => void, onNavigate: Navigate, userId: string}} props
 */
export function DataAssetsPage({ route, notify, onNavigate, userId }) {
  const requestedView = route.query.view || "products";
  const view = ["quality", "returns"].includes(requestedView)
    ? "products"
    : requestedView;
  const taskDraft = readTaskDraft(userId);

  useEffect(() => {
    if (["quality", "returns"].includes(requestedView)) {
      navigateHash("data-assets", { view: "products" });
    }
  }, [requestedView]);
  const focus = useMemo(
    /** @returns {TaskRepairContext | null} */ () => {
      const repair = taskDraft?.repairContext;
      const routeTargetsProduct = route.query.view === "products";
      if ((!route.query.dataset || !routeTargetsProduct) && !repair?.id) return null;
      return {
        ...repair,
        kind: "dataset",
        id: route.query.dataset || repair?.id,
        datasetKind: "products",
        returnToTask: route.query.return_to === "task-create",
      };
    },
    [route.query.dataset, route.query.view, route.query.return_to, taskDraft],
  );

  /** @param {Record<string, string | number>} changes */
  const updateRoute = (changes) =>
    navigateHash("data-assets", { ...route.query, ...changes });

  if (view === "rules") return <ImportRulesPage />;

  return (
    <AntdProvider>
      <ProductMasterWorkspace
        notify={notify}
        onNavigate={onNavigate}
        focus={focus}
        taskDraft={taskDraft}
        routeDetailTab={route.query.tab || ""}
        routeReferenceVersion={route.query.reference_version || ""}
        routeReferencePage={route.query.reference_page || 1}
        onAssetViewChange={(nextView) =>
          updateRoute({ view: nextView, dataset: "", tab: "" })
        }
        onDetailTabChange={(tab) =>
          navigateHash("data-assets", { ...route.query, tab })
        }
        onReferenceRouteChange={(changes) =>
          navigateHash("data-assets", { ...route.query, ...changes })
        }
        onReturnToTask={(productVersionId) => {
          updateTaskDraft(userId, {
            ...taskDraft,
            repairContext: null,
            form: {
              ...taskDraft?.form,
              product_version_id: productVersionId,
            },
            step: 3,
            resumePreflight: true,
          });
          onNavigate("task-create");
        }}
      />
    </AntdProvider>
  );
}
