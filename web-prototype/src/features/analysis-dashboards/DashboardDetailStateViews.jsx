import { ArrowLeft } from "@phosphor-icons/react";

import { InlineLoading } from "../../components/SharedUi";

export function DashboardDetailLoading() {
  return (
    <div className="standard-page analysis-dashboard-page">
      <InlineLoading label="正在读取分析看板…" />
    </div>
  );
}

/** @param {{error: string, onBack: () => void, onReload: () => void | Promise<void>}} props */
export function DashboardDetailError({ error, onBack, onReload }) {
  return (
    <div className="standard-page analysis-dashboard-page">
      <button className="text-button result-back-button" onClick={onBack}>
        <ArrowLeft size={17} /> 返回分析看板
      </button>
      <section className="dashboard-error" role="alert">
        <b>分析看板详情读取失败</b>
        <span>{error}</span>
        <button className="secondary-button" onClick={onReload}>
          重新加载
        </button>
      </section>
    </div>
  );
}
