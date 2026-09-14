import { WarningCircle } from "@phosphor-icons/react";

export function ReviewBatchError({ error, onRetry }) {
  const serviceUnavailable = error?.status === 404;
  return (
    <div className="review-batch-error" role="alert">
      <WarningCircle size={24} />
      <div>
        <b>复核批次读取失败</b>
        <p>
          {serviceUnavailable
            ? "新版复核服务尚不可用，请稍后重新加载"
            : error?.message || "暂时无法读取复核批次"}
        </p>
        {serviceUnavailable && error?.message && (
          <details>
            <summary>查看技术详情</summary>
            <code>{error.message}</code>
          </details>
        )}
      </div>
      <button className="secondary-button" onClick={onRetry}>
        重新加载
      </button>
    </div>
  );
}
