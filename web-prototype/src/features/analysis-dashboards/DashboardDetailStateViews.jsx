import { ArrowLeft } from "@phosphor-icons/react";

import { PageLoadingState } from "../../components/SharedUi";

export function DashboardDetailLoading() {
  return (
    <div className="standard-page analysis-dashboard-page dashboard-detail-page return-insight-page">
      <PageLoadingState title="分析看板" label="正在读取分析看板…" />
    </div>
  );
}

export function DashboardDetailLoadingBody() {
  return <PageLoadingState label="正在读取分析看板…" />;
}

/** @param {{error: string, onBack?: () => void, onReload: () => void | Promise<void>, hasData?: boolean}} props */
export function DashboardDetailError({ error, onBack, onReload, hasData = false }) {
  const alert = (
    <section className={`dashboard-error${hasData ? " is-update" : ""}`} role="alert">
      <b>{hasData ? "分析看板更新失败，当前显示上一次数据" : "分析看板详情读取失败"}</b>
      <span>{error}</span>
      <button className="secondary-button" onClick={onReload}>
        重新加载
      </button>
    </section>
  );
  if (hasData) return alert;
  return (
    <div className="standard-page analysis-dashboard-page">
      <button className="text-button result-back-button" onClick={onBack}>
        <ArrowLeft size={17} /> 返回分析看板
      </button>
      {alert}
    </div>
  );
}
