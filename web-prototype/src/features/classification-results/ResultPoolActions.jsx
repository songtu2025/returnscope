import { DeliveryLifecycleControls } from "../../components/DeliveryLifecycleControls";
import { ResultDownloadButton } from "./ResultDownloadButton";
import { resultActionPolicy } from "./resultActionPolicy";

/** @param {{
 * result: import("../../shared/api/generated/classification-results/types.gen").ClassificationResultVersionResponse,
 * onOpen: () => void,
 * onPrimary: () => void,
 * onChanged?: () => void | Promise<void>
 * }} props */
export function ResultPoolActions({ result, onOpen, onPrimary, onChanged }) {
  const policy = resultActionPolicy(result);
  const deleted = Boolean(result.deleted_at);
  const lifecycle = (
    <DeliveryLifecycleControls
      kind="result"
      id={result.version_id}
      name={result.listing || "分类结果"}
      revision={result.revision || 1}
      deleted={deleted}
      onChanged={onChanged}
    >
      {!deleted && (
        <button
          type="button"
          disabled={policy.primary.disabled}
          title={policy.primary.disabled ? policy.blockingReason : ""}
          onClick={onPrimary}
        >
          {policy.primary.label}
        </button>
      )}
    </DeliveryLifecycleControls>
  );
  const download = (
    <ResultDownloadButton
      key={result.version_id}
      versionId={result.version_id}
      compact
    />
  );
  return (
    <div
      className={`result-row-actions ${deleted ? "is-deleted" : "is-current"}`}
      role="cell"
    >
      <button
        type="button"
        className="text-button compact-button result-open-button"
        onClick={onOpen}
      >
        查看结果
      </button>
      {deleted ? lifecycle : download}
      {deleted ? download : lifecycle}
    </div>
  );
}
