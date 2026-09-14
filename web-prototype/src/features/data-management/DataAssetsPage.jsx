import { useEffect, useMemo } from "react";
import "../../styles/operations.css";
import "../../styles/product-info.css";

import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { DataManagement } from "../../pages/DataManagement";
import { readTaskDraft, updateTaskDraft } from "../task-create/taskDraftStorage";
import { ImportRulesPage } from "./ImportRulesPage";
import { ReturnDataAssetsPage } from "./ReturnDataAssetsPage";

export function DataAssetsPage({ route, notify, onNavigate, userId }) {
  const requestedView = route.query.view || "products";
  const view = requestedView === "quality" ? "products" : requestedView;
  const taskDraft = readTaskDraft(userId);

  useEffect(() => {
    if (requestedView === "quality") {
      navigateHash("data-assets", { view: "products" });
    }
  }, [requestedView]);
  const focus = useMemo(() => {
    const repair = taskDraft?.repairContext ?? {};
    const routeTargetsProduct = route.query.view === "products";
    if ((!route.query.dataset || !routeTargetsProduct) && !repair.id) return null;
    return {
      ...repair,
      kind: "dataset",
      id: route.query.dataset || repair.id,
      datasetKind: "products",
      returnToTask: route.query.return_to === "task-create",
    };
  }, [route.query.dataset, route.query.view, route.query.return_to, taskDraft]);

  const updateRoute = (changes) =>
    navigateHash("data-assets", { ...route.query, ...changes });

  if (view === "returns") {
    return (
      <AntdProvider>
        <ReturnDataAssetsPage
          route={route}
          notify={notify}
          onNavigate={onNavigate}
          onRouteChange={updateRoute}
        />
      </AntdProvider>
    );
  }
  if (view === "rules") return <ImportRulesPage />;

  return (
    <AntdProvider>
      <DataManagement
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
