import { useCallback, useEffect, useMemo, useState } from "react";
import "../../styles/task-flow.css";

import { api } from "../../api";
import { InlineLoading } from "../../components/SharedUi";
import { NewTaskPage } from "./NewTaskPage";
import {
  clearTaskDraft,
  readTaskDraft,
  updateTaskDraft,
  writeTaskDraft,
} from "./taskDraftStorage";

export function TaskCreatePage({ route, notify, onNavigate, onChanged, userId }) {
  const templateTaskId = route.query.template_task;
  const [templateTask, setTemplateTask] = useState(null);
  const [templateLoading, setTemplateLoading] = useState(Boolean(templateTaskId));

  useEffect(() => {
    let active = true;
    if (!templateTaskId) {
      setTemplateTask(null);
      setTemplateLoading(false);
      return () => {
        active = false;
      };
    }
    setTemplateLoading(true);
    api
      .task(templateTaskId)
      .then((task) => {
        if (active) setTemplateTask(task);
      })
      .catch((error) => {
        if (active) {
          setTemplateTask(null);
          notify(`无法读取原任务：${error.message}`, "error");
        }
      })
      .finally(() => {
        if (active) setTemplateLoading(false);
      });
    return () => {
      active = false;
    };
  }, [notify, templateTaskId]);

  const draft = useMemo(() => {
    const stored = readTaskDraft(userId);
    if (templateTask) {
      const config = templateTask.snapshot?.config ?? {};
      const next = {
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
            connection_id: config.connection_id,
            cheap_model: config.cheap_model,
            cheap_effort: config.cheap_effort,
            primary_model: config.primary_model,
            primary_effort: config.primary_effort,
            secondary_model: config.secondary_model,
            secondary_effort: config.secondary_effort,
            cheap_audit_percent: config.cheap_audit_percent,
          },
        },
      };
      writeTaskDraft(userId, next);
      return next;
    }
    if (!route.query.dataset_version) return stored;
    const next = {
      ...stored,
      step: 1,
      resumePreflight: false,
      dataEntryMode: "existing",
      selectedDataLabel: "当前完整数据",
      form: {
        ...stored?.form,
        dataset_version_id: route.query.dataset_version,
      },
    };
    writeTaskDraft(userId, next);
    return next;
  }, [route.query.dataset_version, templateTask, userId]);

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
