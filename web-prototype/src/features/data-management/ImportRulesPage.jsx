import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, ListBullets } from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { dataApi } from "../../shared/api/dataApi";
import { DataAssetTabs } from "./DataAssetTabs";

const KIND_LABELS = {
  returns: "退货数据",
  products: "产品信息",
};

export function ImportRulesPage() {
  const [state, setState] = useState({ loading: true, error: "", items: [] });

  const load = useCallback(async (signal) => {
    setState((current) => ({ ...current, loading: true, error: "" }));
    try {
      const value = await dataApi.importRules({ signal });
      setState({ loading: false, error: "", items: value.items ?? [] });
    } catch (error) {
      if (error.name !== "AbortError") {
        setState({ loading: false, error: error.message, items: [] });
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  return (
    <div className="standard-page data-page import-rules-page">
      <PageHeading
        eyebrow="可复用数据资产"
        title="数据资产"
        description="查看系统当前生效的标准导入规则；规则由系统维护，页面只读。"
      />
      <DataAssetTabs
        current="rules"
        onChange={(view) => navigateHash("data-assets", { view })}
      />

      <section className="content-card import-rules-card">
        <header>
          <div>
            <b>系统导入规则</b>
            <span>上传文件会按对应规则校验扩展名、工作表和字段结构。</span>
          </div>
        </header>
        {state.loading ? (
          <InlineLoading label="正在读取导入规则…" />
        ) : state.error ? (
          <div className="plan-state error import-rules-error" role="alert">
            <div>
              <b>导入规则读取失败</b>
              <p>{state.error}</p>
            </div>
            <button className="secondary-button" onClick={() => load()}>
              <ArrowClockwise size={16} />
              重新加载
            </button>
          </div>
        ) : state.items.length === 0 ? (
          <EmptyState
            icon={ListBullets}
            title="暂无生效的导入规则"
            description="系统提供规则后会显示在这里。"
          />
        ) : (
          <div className="import-rule-list">
            {state.items.map((rule) => (
              <article key={rule.id} className="import-rule-item">
                <header>
                  <div>
                    <span className="status-badge is-ready">
                      {rule.status === "active"
                        ? "生效中"
                        : rule.status || "未提供状态"}
                    </span>
                    <h3>{rule.name}</h3>
                    <p>
                      {KIND_LABELS[rule.kind] ?? rule.kind ?? "未提供适用资产"} · v
                      {rule.version ?? "-"}
                    </p>
                  </div>
                  <code>{rule.id}</code>
                </header>
                <dl>
                  <RuleField
                    label="文件扩展名"
                    value={formatValues(rule.file_extensions)}
                  />
                  <RuleField label="工作表" value={rule.worksheet || "未限制"} />
                  <RuleField
                    label="必需字段"
                    value={formatValues(rule.required_columns)}
                  />
                  <RuleField
                    label="可选字段"
                    value={formatValues(rule.optional_columns)}
                  />
                  <RuleField label="匹配键" value={formatValues(rule.match_key)} />
                  <RuleField label="说明" value={formatValues(rule.notes)} />
                </dl>
                <details className="quality-technical-details">
                  <summary>技术信息</summary>
                  <code>content_hash: {rule.content_hash || "未提供"}</code>
                  <code>source: {rule.source || "未提供"}</code>
                </details>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RuleField({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function formatValues(value) {
  if (Array.isArray(value)) return value.length ? value.join("、") : "无";
  return value || "未提供";
}
