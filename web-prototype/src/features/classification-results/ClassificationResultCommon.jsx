import { WarningCircle } from "@phosphor-icons/react";

export { Pagination } from "../../components/Pagination";

/** @param {{ message: string, onRetry: () => void }} props */
export function ResultError({ message, onRetry }) {
  return (
    <div className="result-error-state" role="alert">
      <WarningCircle size={24} />
      <div>
        <b>分类结果读取失败</b>
        <p>{message}</p>
      </div>
      <button className="secondary-button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}
