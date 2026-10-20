import { useEffect, useMemo } from "react";
import "../../styles/operations.css";
import "../../styles/product-info.css";
import { navigateHash, parseHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { ProductMasterWorkspace } from "./ProductMasterWorkspace";
import { readTaskDraft, updateTaskDraft } from "../task-create/taskDraftStorage";
import { ImportRulesPage } from "./ImportRulesPage";
import { productResultReturnQuery } from "../classification-results/classificationResultRoute";
import { productAuditReturnQuery } from "./productAuditRoute";

/** @typedef {import("./productMasterContracts").Navigate} Navigate */
/** @typedef {import("./productMasterContracts").TaskRepairContext} TaskRepairContext */
/** @typedef {{query: {view?: string, dataset?: string, return_to?: string, tab?: string, reference_version?: string, reference_page?: string | number, result_return?: string, audit_return?: string}}} DataAssetsRoute */

/**
 * @param {{route: DataAssetsRoute, notify: (message: string, tone?: string) => void, onNavigate: Navigate, userId: string, returnPosition?: import("react").MutableRefObject<import("../../hooks/useListReturnPosition").ListReturnPosition | null>}} props
 */
export function DataAssetsPage({ route, notify, onNavigate, userId, returnPosition }) {
  const requestedView = route.query.view || "products";
  const view = ["quality", "returns"].includes(requestedView)
    ? "products"
    : requestedView;
  const taskDraft = readTaskDraft(userId);
  const resultReturn = productResultReturnQuery(route.query.result_return);
  const auditReturn = route.query.audit_return
    ? productAuditReturnQuery(parseHash(route.query.audit_return))
    : null;

  useEffect(() => {
    if (["quality", "returns"].includes(requestedView)) {
      navigateHash("data-assets", { view: "products" });
    } else if (route.query.reference_version) {
      navigateHash(
        "data-assets",
        { ...route.query, reference_version: "" },
        { replace: true },
      );
    }
  }, [requestedView, route.query]);
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
    navigateHash("data-assets", {
      ...route.query,
      ...changes,
      reference_version: "",
    });

  if (view === "rules") return <ImportRulesPage />;

  return (
    <AntdProvider>
      <ProductMasterWorkspace
        onReturnAudit={
          auditReturn ? () => navigateHash("data-assets", auditReturn) : undefined
        }
        onReturnResult={
          resultReturn
            ? () => navigateHash("classification-results", resultReturn)
            : undefined
        }
        returnPosition={returnPosition}
        notify={notify}
        onNavigate={onNavigate}
        focus={focus}
        taskDraft={taskDraft}
        routeDetailTab={route.query.tab || ""}
        routeReferencePage={route.query.reference_page || 1}
        onAssetViewChange={(nextView) =>
          updateRoute({ view: nextView, dataset: "", tab: "" })
        }
        onDetailTabChange={(tab) => updateRoute({ tab })}
        onReferenceRouteChange={updateRoute}
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
