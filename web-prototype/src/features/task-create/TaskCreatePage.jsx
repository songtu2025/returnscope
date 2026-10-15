import { MANAGED_REFRESH_OPTIONS } from "../../shared/refreshPolicy";
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import "../../styles/task-flow.css";
import useSWR from "swr";

import { api } from "../../api";
import { Modal, PageLoadingState } from "../../components/SharedUi";
import { serverStateKeys } from "../../shared/serverState";
import { PageLoadingContext } from "../../hooks/usePageLoading";
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
 * @param {{route: import("../../app/navigation").AppRoute, notify: (message: string, type?: "success" | "error") => void, onNavigate: import("../../app/navigation").Navigate, onChanged: () => void | Promise<unknown>, userId: string, canManageModels?: boolean}} props
 */

export function TaskCreatePage(props) {
  const { userId, route } = props;
  return (
    <TaskCreateSession
      key={`${userId}:${route.query.template_task ?? ""}:${route.query.dataset_version ?? ""}`}
      {...props}
    />
  );
}

/** @param {Parameters<typeof TaskCreatePage>[0]} props */
function TaskCreateSession({
  route,
  notify,
  onNavigate,
  onChanged,
  userId,
  canManageModels = false,
}) {
  const pageLoading = useContext(PageLoadingContext);
  const templateTaskId = route.query.template_task;
  const {
    data: templateTask = null,
    error: templateError,
    isLoading: templateLoading,
  } = useSWR(
    templateTaskId ? serverStateKeys.taskTemplate(templateTaskId) : null,
    () => (templateTaskId ? api.task(templateTaskId) : null),
    MANAGED_REFRESH_OPTIONS,
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

  const migrationNotified = useRef(false);
  const [templateChoice, setTemplateChoice] = useState({ id: "", replace: false });
  const stored = useMemo(() => readTaskDraft(userId), [userId]);
  const choiceMade = templateChoice.id === templateTaskId;
  const needsChoice = Boolean(templateTask && stored && !choiceMade);
  const { draft, requiresMigration } = useMemo(
    /** @returns {{draft: TaskDraft | null, requiresMigration: boolean}} */ () => {
      if (templateTask && (!stored || (choiceMade && templateChoice.replace))) {
        const config = /** @type {Partial<TaskModelPolicy>} */ (
          templateTask.snapshot?.config ?? {}
        );
        const next = /** @type {TaskDraft} */ ({
          step: 1,
          resumePreflight: false,
          dataEntryMode: "mysql",
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
        return { draft: next, requiresMigration: false };
      }
      // 迁移判定与草稿同时读取，避免子组件保存后丢失旧来源信息。
      const requiresMigration = Boolean(
        route.query.dataset_version ||
        (stored &&
          stored.dataEntryMode !== "mysql" &&
          stored.dataEntryMode !== "upload"),
      );
      if (requiresMigration) {
        /** @type {TaskDraft | null} */
        const migratedDraft = stored
          ? {
              ...stored,
              step: 1,
              resumePreflight: false,
              dataEntryMode: "mysql",
              selectedDataLabel: "",
              form: { ...stored.form, dataset_version_id: "" },
            }
          : null;
        return { draft: migratedDraft, requiresMigration };
      }
      return { draft: stored, requiresMigration: false };
    },
    [
      route.query.dataset_version,
      templateTask,
      stored,
      choiceMade,
      templateChoice.replace,
    ],
  );

  useEffect(() => {
    if (!requiresMigration) migrationNotified.current = false;
    if (
      requiresMigration &&
      !migrationNotified.current &&
      !templateLoading &&
      !needsChoice
    ) {
      migrationNotified.current = true;
      if (draft) writeTaskDraft(userId, draft);
      notify(
        "已有数据源入口已下线，请重新读取数据库或上传文件；其他草稿设置已保留。",
        "error",
      );
    }
  }, [draft, notify, requiresMigration, userId, templateLoading, needsChoice]);

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

  const continueDraft = () =>
    setTemplateChoice({ id: templateTaskId ?? "", replace: false });

  return templateLoading ? (
    <div className="standard-page new-task-page">
      <PageLoadingState title="创建分析任务" label="正在读取原任务配置…" />
    </div>
  ) : needsChoice ? (
    <div className="standard-page new-task-page">
      <h1>创建分析任务</h1>
      {!pageLoading?.initial && (
        <Modal title="保留已有任务草稿？" onClose={continueDraft}>
          <div className="modal-form">
            <p>
              已有草稿“{stored?.form?.title || "未命名任务"}”。用“{templateTask?.title}
              ”创建类似任务将替换草稿，原输入无法恢复。
            </p>
            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={() => {
                  setTemplateChoice({ id: templateTaskId ?? "", replace: true });
                }}
              >
                替换草稿并创建类似任务
              </button>
              <button className="primary-button" onClick={continueDraft}>
                继续已有草稿
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  ) : (
    <NewTaskPage
      key={templateTask?.id ?? "new-task"}
      onNavigate={navigate}
      canManageModels={canManageModels}
      notify={notify}
      onChanged={onChanged}
      draft={draft}
      onDraftChange={(next) => writeTaskDraft(userId, next)}
      onDraftComplete={() => clearTaskDraft(userId)}
      onDiscard={() => {
        clearTaskDraft(userId);
        onNavigate("tasks");
      }}
    />
  );
}
