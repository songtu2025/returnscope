import { WarningCircle } from "@phosphor-icons/react";

export { Pagination } from "../../components/Pagination";

/** @param {{ message: string, onRetry: () => void, hasData?: boolean }} props */
export function ResultError({ message, onRetry, hasData = false }) {
  return (
    <div className="result-error-state" role="alert">
      <WarningCircle size={24} />
      <div>
        <b>{hasData ? "分类结果更新失败，当前显示上一次数据" : "分类结果读取失败"}</b>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}
