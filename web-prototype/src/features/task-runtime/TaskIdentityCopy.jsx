import "./taskIdentityCopy.css";
import { useState } from "react";
import { CopySimple } from "@phosphor-icons/react";

/** @param {{id: string}} props */
export function TaskIdentityCopy({ id }) {
  const [message, setMessage] = useState("");
  return (
    <div className="task-identity-copy">
      <code title={id}>{id}</code>
      <button
        type="button"
        className="icon-button"
        aria-label={`复制任务 ID：${id}`}
        title="复制任务 ID"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(id);
            setMessage("已复制");
          } catch {
            setMessage("复制失败，请选择 ID 手动复制");
          }
        }}
      >
        <CopySimple size={15} />
      </button>
      <small role="status">{message}</small>
    </div>
  );
}
