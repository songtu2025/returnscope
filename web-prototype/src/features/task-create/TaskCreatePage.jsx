import { useCallback, useMemo } from "react";

import { NewTaskPage } from "./NewTaskPage";
import {
  clearTaskDraft,
  readTaskDraft,
  updateTaskDraft,
  writeTaskDraft,
} from "./taskDraftStorage";

export function TaskCreatePage({ route, notify, onNavigate, onChanged, userId }) {
  const draft = useMemo(() => {
    const stored = readTaskDraft(userId);
    if (!route.query.dataset_version) return stored;
    const next = {
      ...stored,
      form: {
        ...stored?.form,
        dataset_version_id: route.query.dataset_version,
      },
    };
    writeTaskDraft(userId, next);
    return next;
  }, [route.query.dataset_version, userId]);

  const navigate = useCallback(
    (destination, focus) => {
      if (destination === "data" && focus?.returnToTask) {
        updateTaskDraft(userId, { repairContext: focus });
      }
      onNavigate(destination, focus);
    },
    [onNavigate, userId],
  );

  return (
    <>
      <nav className="page-breadcrumb" aria-label="面包屑">
        <button onClick={() => onNavigate("analysis-tasks")}>分析任务</button>
        <span aria-hidden="true">/</span>
        <span>创建任务</span>
      </nav>
      <NewTaskPage
        onNavigate={navigate}
        notify={notify}
        onChanged={onChanged}
        draft={draft}
        onDraftChange={(next) => writeTaskDraft(userId, next)}
        onDraftComplete={() => clearTaskDraft(userId)}
      />
    </>
  );
}
