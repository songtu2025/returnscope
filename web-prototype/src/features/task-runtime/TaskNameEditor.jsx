import { useRef, useState } from "react";
import { PencilSimple } from "@phosphor-icons/react";
import { taskMonitorApi, errorMessage, errorStatus } from "./taskMonitorRequests";
import "./taskNameEditor.css";
/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @param {{task: AnalysisTask, onSaved: (task: AnalysisTask) => Promise<unknown>, onOpen?: () => void, heading?: boolean, disabled?: boolean}} props */
export function TaskNameEditor({
  task,
  onSaved,
  onOpen,
  heading = false,
  disabled = false,
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [revision, setRevision] = useState(task.revision);
  const [baseTitle, setBaseTitle] = useState(task.title);
  const [conflict, setConflict] = useState(false);
  const [latest, setLatest] = useState(/** @type {AnalysisTask | null} */ (null));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const editRef = useRef(/** @type {HTMLButtonElement | null} */ (null));
  const cancel = () => {
    if (saving) return;
    setEditing(false);
    setError("");
    window.requestAnimationFrame(() => editRef.current?.focus());
  };
  const readLatest = async () => {
    setLatest(null);
    try {
      setLatest(await taskMonitorApi.task(task.id));
      setError("任务名称已被修改，请核对后选择采用的名称。");
    } catch {
      setError("任务资料读取失败，输入已保留，请重新读取后核对");
    }
  };
  const retryLatest = async () => {
    setSaving(true);
    try {
      await readLatest();
    } finally {
      setSaving(false);
    }
  };
  /** @param {AnalysisTask} updated */
  const finish = async (updated) => {
    setEditing(false);
    setConflict(false);
    setError("");
    try {
      await onSaved(updated);
    } catch {
      setError("名称已确认，页面更新失败，请刷新页面");
    }
  };
  /** @param {import("react").FormEvent<HTMLFormElement>} event */
  const submit = async (event) => {
    event.preventDefault();
    if (disabled) return;
    if (saving || conflict) return;
    const name = title.trim();
    if (!name) {
      setError("任务名称不能为空");
      return;
    }
    if (name === baseTitle) {
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
        setConflict(true);
        await readLatest();
      }
      setSaving(false);
      return;
    }
    setSaving(false);
    await finish(updated);
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
            disabled={saving || disabled}
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
              disabled={saving || disabled || conflict || !title.trim()}
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
          {conflict && (
            <section className="task-name-conflict" aria-label="任务名称冲突核对">
              {latest ? (
                <>
                  <dl>
                    <dt>最新名称</dt>
                    <dd>{latest.title}</dd>
                    <dt>我的名称</dt>
                    <dd>{title.trim() || "--"}</dd>
                  </dl>
                  {title.trim() === latest.title ? (
                    <p role="status">最新名称与我的输入一致，无需再次保存。</p>
                  ) : (
                    <button
                      type="button"
                      className="text-button"
                      disabled={saving || disabled || !title.trim()}
                      onClick={() => {
                        setRevision(latest.revision);
                        setBaseTitle(latest.title);
                        setConflict(false);
                        setLatest(null);
                        setError("");
                      }}
                    >
                      采用我的名称
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-button"
                    disabled={saving || disabled}
                    onClick={() => finish(latest)}
                  >
                    采用最新名称
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="text-button"
                  disabled={saving}
                  onClick={retryLatest}
                >
                  {saving ? "读取中…" : "重新读取任务"}
                </button>
              )}
            </section>
          )}
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
            title="修改任务名称"
            disabled={disabled}
            onClick={() => {
              setTitle(task.title);
              setRevision(task.revision);
              setBaseTitle(task.title);
              setConflict(false);
              setLatest(null);
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
