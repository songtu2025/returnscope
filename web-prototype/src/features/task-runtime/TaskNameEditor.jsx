import { useRef, useState } from "react";
import { PencilSimple } from "@phosphor-icons/react";
import { taskMonitorApi, errorMessage, errorStatus } from "./taskMonitorRequests";
/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @param {{task: AnalysisTask, onSaved: (task: AnalysisTask) => Promise<unknown>, onOpen?: () => void, heading?: boolean}} props */
export function TaskNameEditor({ task, onSaved, onOpen, heading = false }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [revision, setRevision] = useState(task.revision);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const editRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const cancel = () => {
    if (saving) return;
    setEditing(false);
    setError("");
    window.requestAnimationFrame(() => editRef.current?.focus());
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    const name = title.trim();
    if (!name) {
      setError("任务名称不能为空");
      return;
    }
    if (name === task.title) {
      cancel();
      return;
    }
    setSaving(true);
    setError("");
    let updated;
    try {
      updated = await taskMonitorApi.renameTask(task.id, {
        title: name,
        expected_revision: revision,
      });
    } catch (failure) {
      setError(errorMessage(failure));
      if (errorStatus(failure) === 409) {
        try {
          const latest = await taskMonitorApi.task(task.id);
          setRevision(latest.revision);
        } catch {
          setError("任务资料读取失败，输入已保留，请稍后重试");
        }
      }
      setSaving(false);
      return;
    }
    setEditing(false);
    setSaving(false);
    try {
      await onSaved(updated);
    } catch {
      setError("名称已保存，页面更新失败，请刷新页面");
    }
  };
  return (
    <div className={`task-name-editor${heading ? " is-heading" : ""}`}>
      {editing ? (
        <form onSubmit={submit}>
          <input
            aria-label="任务名称"
            value={title}
            maxLength={120}
            autoFocus
            disabled={saving}
            aria-invalid={Boolean(error)}
            onChange={(event) => setTitle(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                cancel();
              }
            }}
          />
          <div className="task-name-edit-actions">
            <button
              type="submit"
              className="text-button"
              disabled={saving || !title.trim()}
            >
              {saving ? "保存中…" : "保存名称"}
            </button>
            <button
              type="button"
              className="text-button"
              disabled={saving}
              onClick={cancel}
            >
              取消改名
            </button>
          </div>
        </form>
      ) : (
        <div className="task-name-display">
          {heading ? (
            <h2>{task.title}</h2>
          ) : (
            <button
              type="button"
              className="task-name-open"
              title={task.title}
              onClick={onOpen}
            >
              <b>{task.title}</b>
            </button>
          )}
          <button
            ref={editRef}
            type="button"
            className="task-rename-action"
            aria-label={`修改任务名称：${task.title}`}
            title="修改名称"
            onClick={() => {
              setTitle(task.title);
              setRevision(task.revision);
              setError("");
              setEditing(true);
            }}
          >
            <PencilSimple size={16} />
          </button>
        </div>
      )}
      {error && (
        <p className="task-name-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
