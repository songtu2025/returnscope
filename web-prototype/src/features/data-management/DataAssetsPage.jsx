import { useMemo } from "react";

import { navigateHash } from "../../app/hashRouter";
import { DataManagement } from "../../pages/DataManagement";
import { readTaskDraft, updateTaskDraft } from "../task-create/taskDraftStorage";

export function DataAssetsPage({ route, notify, onNavigate, userId }) {
  const taskDraft = readTaskDraft(userId);
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

  return (
    <DataManagement
      notify={notify}
      onNavigate={onNavigate}
      focus={focus}
      taskDraft={taskDraft}
      routeDetailTab={route.query.tab || ""}
      routeReferenceVersion={route.query.reference_version || ""}
      routeReferencePage={route.query.reference_page || 1}
      onDetailTabChange={(tab) => navigateHash("data-assets", { ...route.query, tab })}
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
  );
}
