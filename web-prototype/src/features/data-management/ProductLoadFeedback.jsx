import { ArrowClockwise } from "@phosphor-icons/react";
import Button from "antd/es/button";
import { InlineLoading } from "../../components/SharedUi";

/** @param {{error: unknown, loading: boolean, hasData?: boolean, label?: string, onRetry: () => Promise<unknown>}} props */
export function ProductLoadFeedback({
  error,
  loading,
  hasData = false,
  label = "读取产品信息…",
  onRetry,
}) {
  if (!error) return loading && !hasData ? <InlineLoading label={label} /> : null;
  return (
    <div className="plan-state error" role="alert">
      <div>
        <b>
          {hasData
            ? "产品信息刷新失败，当前显示上次成功读取的内容"
            : "产品信息读取失败"}
        </b>
        <p>{error instanceof Error ? error.message : "请求失败，请重试"}</p>
      </div>
      <Button
        icon={<ArrowClockwise size={16} />}
        disabled={loading}
        onClick={() => onRetry()}
      >
        重试
      </Button>
    </div>
  );
}
