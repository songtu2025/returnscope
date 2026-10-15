import { useState } from "react";
import {
  semanticChanges,
  restoreSemanticChange,
} from "../../shared/api/historyRestore";
import { HistoryRestoreButton } from "../../components/HistoryRestoreButton";
import { errorMessage } from "../../shared/api/requestErrors";
import { formatTime } from "../../lib/presentation";

/** @param {{versionId: string, recordId: string, onSaved: (id: string) => void, onBusyChange: (busy: boolean) => void}} props */
export function SemanticHistory({ versionId, recordId, onSaved, onBusyChange }) {
  const [entries, setEntries] = useState(
    /** @type {import("../../shared/api/historyRestore").SemanticChange[] | null} */ (
      null
    ),
  );
  const [error, setError] = useState("");
  const load = async () => {
    try {
      setEntries(await semanticChanges(versionId, recordId));
      setError("");
    } catch (failure) {
      setError(errorMessage(failure));
    }
  };
  return (
    <section className="drawer-section">
      <button
        className="secondary-button"
        onClick={() => (entries ? setEntries(null) : void load())}
      >
        {entries ? "收起修正历史" : "查看修正历史"}
      </button>
      {entries?.map((entry) => (
        <div key={entry.id}>
          <b>
            {entry.actor_name} · {formatTime(entry.created_at)}
          </b>
          <p>
            修改前：
            {entry.before.semantic_units
              ?.map((unit) => `${unit.label_code} ${unit.opinion ?? ""}`)
              .join("；") || "未形成语义观点"}
          </p>
          <HistoryRestoreButton
            onRestore={async () => {
              onBusyChange(true);
              try {
                const result = await restoreSemanticChange(
                  versionId,
                  recordId,
                  entry.id,
                );
                onSaved(result.version_id);
              } finally {
                onBusyChange(false);
              }
            }}
          />
        </div>
      ))}
      {entries?.length === 0 && <p>暂无人工修正记录</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
