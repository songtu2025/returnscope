import { useCallback, useEffect, useMemo } from "react";
import "../../styles/task-flow.css";
import useSWR from "swr";

import { api } from "../../api";
import { InlineLoading } from "../../components/SharedUi";
import { serverStateKeys } from "../../shared/serverState";
import { NewTaskPage } from "./NewTaskPage";
import {
  clearTaskDraft,
  readTaskDraft,
  updateTaskDraft,
  writeTaskDraft,
} from "./taskDraftStorage";

/** @typedef {import("./taskCreateContracts").TaskDraft} TaskDraft */
/** @typedef {import("./taskCreateContracts").TaskModelPolicy} TaskModelPolicy */
/** @typedef {import("../task-runtime/taskRuntimeContracts").AnalysisTask} AnalysisTask */
/**
 * @param {{route: import("../../app/navigation").AppRoute, notify: (message: string, type?: "success" | "error") => void, onNavigate: import("../../app/navigation").Navigate, onChanged: () => void | Promise<unknown>, userId: string}} props
 */

export function TaskCreatePage({ route, notify, onNavigate, onChanged, userId }) {
  const templateTaskId = route.query.template_task;
  const {
    data: templateTask = null,
    error: templateError,
    isLoading: templateLoading,
  } = useSWR(
    templateTaskId ? serverStateKeys.taskTemplate(templateTaskId) : null,
    () => (templateTaskId ? api.task(templateTaskId) : null),
  );

  useEffect(() => {
    if (!templateError) return;
    notify(
      `无法读取原任务：${
        templateError instanceof Error ? templateError.message : "请求失败"
      }`,
      "error",
    );
  }, [notify, templateError]);

  const draft = useMemo(() => {
    const stored = readTaskDraft(userId);
    if (templateTask) {
      const config = /** @type {Partial<TaskModelPolicy>} */ (
        templateTask.snapshot?.config ?? {}
      );
      const next = /** @type {TaskDraft} */ ({
        step: 1,
        resumePreflight: false,
        dataEntryMode: "existing",
        selectedDataLabel: "",
        form: {
          title: `${templateTask.title}（副本）`.slice(0, 120),
          dataset_version_id: "",
          product_version_id: "",
          config_version_id: templateTask.config_version_id,
          store: "",
          listing: "",
          model_policy: {
            connection_id: config.connection_id ?? "",
            cheap_model: config.cheap_model ?? "",
            cheap_effort: config.cheap_effort ?? "low",
            primary_model: config.primary_model ?? "",
            primary_effort: config.primary_effort ?? "medium",
            secondary_model: config.secondary_model ?? "",
            secondary_effort: config.secondary_effort ?? "high",
            cheap_audit_percent: config.cheap_audit_percent ?? 5,
          },
        },
      });
      writeTaskDraft(userId, next);
      return next;
    }
    if (!route.query.dataset_version) return stored;
    const next = /** @type {TaskDraft} */ ({
      ...stored,
      step: 1,
      resumePreflight: false,
      dataEntryMode: "existing",
      selectedDataLabel: "当前完整数据",
      form: {
        ...stored?.form,
        dataset_version_id: route.query.dataset_version,
      },
    });
    writeTaskDraft(userId, next);
    return next;
  }, [route.query.dataset_version, templateTask, userId]);

  const navigate = useCallback(
    /** @type {import("../../app/navigation").Navigate} */
    (destination, focus) => {
      if (destination === "data" && focus?.kind === "dataset" && focus.returnToTask) {
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
      {templateLoading ? (
        <section className="content-card task-template-loading">
          <InlineLoading label="正在读取原任务配置…" />
        </section>
      ) : (
        <NewTaskPage
          key={templateTask?.id ?? "new-task"}
          onNavigate={navigate}
          notify={notify}
          onChanged={onChanged}
          draft={draft}
          onDraftChange={(next) => writeTaskDraft(userId, next)}
          onDraftComplete={() => clearTaskDraft(userId)}
        />
      )}
    </>
  );
}
