import { DotsThreeVertical } from "@phosphor-icons/react";
import { useDismissibleDetails } from "../../hooks/useDismissibleDetails";

/** @param {{item: import("./taskRecycleContracts").RecycledListing, disabled: boolean, onRestore: () => void, onPurge: () => void}} props */
export function TaskRecycleRowActions({ item, disabled, onRestore, onPurge }) {
  const { detailsProps, summaryProps } = useDismissibleDetails({
    menu: true,
    disabled,
  });
  const name = `${item.scope.listing || "Listing"} · ${item.scope.store || "未提供店铺"}`;
  return (
    <div className="recycle-actions">
      <button
        className="secondary-button compact-button"
        disabled={disabled}
        aria-label={`恢复 ${name}`}
        onClick={onRestore}
      >
        恢复
      </button>
      <details {...detailsProps} className="recycle-more">
        <summary
          {...summaryProps}
          className="secondary-button compact-button"
          aria-label={`更多回收站操作：${name}`}
        >
          <DotsThreeVertical size={18} />
        </summary>
        <div hidden={!detailsProps.open}>
          <button
            type="button"
            className="text-button danger"
            disabled={disabled}
            onClick={onPurge}
          >
            永久删除
          </button>
        </div>
      </details>
    </div>
  );
}
