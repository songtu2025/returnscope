import { CaretRight } from "@phosphor-icons/react";
import Button from "antd/es/button";
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
    <div className={`result-row-actions${deleted ? "" : " is-current"}`} role="cell">
      {deleted ? (
        <>
          {lifecycle}
          <Button
            size="small"
            disabled={policy.primary.disabled}
            title={policy.blockingReason}
            icon={<CaretRight size={15} />}
            iconPlacement="end"
            onClick={onPrimary}
          >
            {policy.primary.label}
          </Button>
          {download}
        </>
      ) : (
        <>
          <button
            type="button"
            className="text-button compact-button result-open-button"
            onClick={onOpen}
          >
            查看结果
          </button>
          {download}
          {lifecycle}
        </>
      )}
    </div>
  );
}
