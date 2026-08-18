import { useCallback, useEffect, useState } from "react";
import {
  ArrowClockwise,
  ArrowRight,
  ClockCounterClockwise,
} from "@phosphor-icons/react";

import { navigateHash } from "../../app/hashRouter";
import { routeForTarget } from "../../app/navigation";
import { EmptyState, InlineLoading, PageHeading } from "../../components/SharedUi";
import { formatTime } from "../../lib/presentation";
import { auditApi } from "../../shared/api/auditApi";

const PAGE_SIZE = 20;
const SENSITIVE_FIELD = /(password|secret|token|api[_-]?key|encryption[_-]?key)/i;
const ACTION_LABELS = {
  task_create: "创建任务",
  task_pause: "暂停任务",
  task_resume: "继续任务",
  task_cancel: "取消任务",
  segment_pause: "暂停 Listing",
  segment_resume: "继续 Listing",
  segment_cancel: "取消 Listing",
  segment_retry: "重试 Listing",
  review_update: "更新复核记录",
  review_batch_update: "更新复核批次",
  review_batch_publish: "发布复核版本",
  legacy_result_backfill_prepare: "准备回填历史结果",
  config_publish: "发布模型配置",
  user_update: "更新用户",
};
const ENTITY_LABELS = {
  task: "分析任务",
  task_segment: "Listing 片段",
  review: "历史复核记录",
  review_batch: "复核批次",
  dataset: "数据资产",
  data_version: "数据版本",
  api_connection: "API 接入",
  config_version: "模型配置版本",
  model: "模型",
  user: "用户",
  classification_result: "分类结果",
  analysis_dashboard: "分析看板",
};
const FIELD_LABELS = {
  status: "状态",
  revision: "修订版本",
  reason: "原因",
  note: "备注",
  actor: "操作人",
  preview_hash: "预检哈希",
  plan_hash: "执行计划哈希",
  result_publish_status: "结果发布状态",
  segment_id: "Listing 片段 ID",
  max_parallel_segments: "Listing 并行数",
  execution_order: "执行顺序",
};

function numberParam(value, fallback = 1) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function writeAuditRoute(route, changes) {
  navigateHash("settings", {
    tab: "audit",
    actor_id: route.query.actor_id || "",
    entity_type: route.query.entity_type || "",
    entity_id: route.query.entity_id || "",
    action: route.query.action || "",
    date_from: route.query.date_from || "",
    date_to: route.query.date_to || "",
    page: numberParam(route.query.page) > 1 ? route.query.page : "",
    ...changes,
  });
}

export function AuditLogPage({ route }) {
  const page = numberParam(route.query.page);
  const [draft, setDraft] = useState(() => filtersFromRoute(route));
  const [state, setState] = useState({ loading: true, error: "", data: null });

  useEffect(() => setDraft(filtersFromRoute(route)), [route]);

  const load = useCallback(
    async (signal) => {
      setState({ loading: true, error: "", data: null });
      try {
        const data = await auditApi.logs(
          {
            actor_id: route.query.actor_id || "",
            entity_type: route.query.entity_type || "",
            entity_id: route.query.entity_id || "",
            action: route.query.action || "",
            date_from: route.query.date_from || "",
            date_to: route.query.date_to || "",
            page,
            page_size: PAGE_SIZE,
          },
          { signal },
        );
        setState({ loading: false, error: "", data });
      } catch (error) {
        if (error.name !== "AbortError") {
          setState({ loading: false, error: error.message, data: null });
        }
      }
    },
    [page, route.query],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const total = Number(state.data?.total ?? 0);
  const pages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <div className="standard-page audit-page">
      <PageHeading
        eyebrow="系统治理"
        title="审计记录"
        description="按操作人、对象和日期追溯系统变更；敏感字段始终掩码。"
      />
      <section className="content-card audit-card">
        <form
          className="audit-filter-form"
          onSubmit={(event) => {
            event.preventDefault();
            writeAuditRoute(route, { ...draft, page: "" });
          }}
        >
          <label>
            操作人 ID
            <input
              value={draft.actor_id}
              onChange={(event) => setDraft({ ...draft, actor_id: event.target.value })}
            />
          </label>
          <label>
            对象类型
            <input
              value={draft.entity_type}
              onChange={(event) =>
                setDraft({ ...draft, entity_type: event.target.value })
              }
              placeholder="如 task"
            />
          </label>
          <label>
            对象 ID
            <input
              value={draft.entity_id}
              onChange={(event) =>
                setDraft({ ...draft, entity_id: event.target.value })
              }
            />
          </label>
          <label>
            动作
            <input
              value={draft.action}
              onChange={(event) => setDraft({ ...draft, action: event.target.value })}
            />
          </label>
          <label>
            开始日期
            <input
              type="date"
              value={draft.date_from}
              onChange={(event) =>
                setDraft({ ...draft, date_from: event.target.value })
              }
            />
          </label>
          <label>
            结束日期
            <input
              type="date"
              value={draft.date_to}
              onChange={(event) => setDraft({ ...draft, date_to: event.target.value })}
            />
          </label>
          <button className="primary-button">筛选</button>
        </form>

        {state.loading ? (
          <InlineLoading label="正在读取审计记录…" />
        ) : state.error ? (
          <div className="plan-state error audit-error" role="alert">
            <div>
              <b>审计记录读取失败</b>
              <p>{state.error}</p>
            </div>
            <button className="secondary-button" onClick={() => load()}>
              <ArrowClockwise size={16} />
              重新加载
            </button>
          </div>
        ) : !state.data?.items?.length ? (
          <EmptyState
            icon={ClockCounterClockwise}
            title="当前筛选没有审计记录"
            description="可调整操作人、对象、动作或日期范围。"
          />
        ) : (
          <>
            <div className="audit-list">
              {state.data.items.map((item) => (
                <article key={item.id}>
                  <header>
                    <div>
                      <b>{item.actor_name || "未提供操作人"}</b>
                      <AuditTerm
                        value={item.action}
                        labels={ACTION_LABELS}
                        fallback="未提供动作"
                      />
                    </div>
                    <time>{formatTime(item.created_at)}</time>
                  </header>
                  <div className="audit-object-line">
                    <span className="audit-object-identity">
                      <AuditTerm
                        value={item.entity_type}
                        labels={ENTITY_LABELS}
                        fallback="未提供对象"
                      />
                      <span>· {item.entity_id || "未提供 ID"}</span>
                    </span>
                    {item.target?.route && (
                      <button
                        className="text-button"
                        onClick={() => {
                          const destination = routeForTarget(item.target);
                          if (destination) {
                            navigateHash(destination.page, destination.query);
                          }
                        }}
                      >
                        查看对象 <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
                  <AuditDiff before={item.before} after={item.after} />
                </article>
              ))}
            </div>
            <footer className="quality-pagination">
              <span>
                共 {total.toLocaleString()} 条 · 第 {page}/{pages} 页
              </span>
              <button
                className="secondary-button"
                disabled={page <= 1}
                onClick={() => writeAuditRoute(route, { page: page - 1 })}
              >
                上一页
              </button>
              <button
                className="secondary-button"
                disabled={page >= pages}
                onClick={() => writeAuditRoute(route, { page: page + 1 })}
              >
                下一页
              </button>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}

function AuditDiff({ before, after }) {
  const beforeFields = flattenObject(before);
  const afterFields = flattenObject(after);
  const keys = Array.from(
    new Set([...Object.keys(beforeFields), ...Object.keys(afterFields)]),
  ).sort();
  if (!keys.length) return <p className="muted-line">本次操作没有字段差异明细。</p>;
  return (
    <details className="audit-diff">
      <summary>查看字段差异</summary>
      <div className="audit-diff-table">
        <div className="table-head">
          <span>字段</span>
          <span>修改前</span>
          <span>修改后</span>
        </div>
        {keys.map((key) => (
          <div key={key}>
            <span className="audit-field-name">
              <b>{FIELD_LABELS[key] ?? key}</b>
              {FIELD_LABELS[key] && <code>{key}</code>}
            </span>
            <span>{displayAuditValue(key, beforeFields[key])}</span>
            <span>{displayAuditValue(key, afterFields[key])}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

function AuditTerm({ value, labels, fallback }) {
  if (!value) return <span>{fallback}</span>;
  const label = labels[value];
  return (
    <span className="audit-technical-term">
      {label ?? value}
      {label && <code>{value}</code>}
    </span>
  );
}

function filtersFromRoute(route) {
  return {
    actor_id: route.query.actor_id || "",
    entity_type: route.query.entity_type || "",
    entity_id: route.query.entity_id || "",
    action: route.query.action || "",
    date_from: route.query.date_from || "",
    date_to: route.query.date_to || "",
  };
}

function flattenObject(value, prefix = "", result = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    if (prefix) result[prefix] = value;
    return result;
  }
  Object.entries(value).forEach(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === "object" && !Array.isArray(child)) {
      flattenObject(child, path, result);
    } else {
      result[path] = child;
    }
  });
  return result;
}

function displayAuditValue(field, value) {
  if (SENSITIVE_FIELD.test(field)) return "••••••";
  if (value === null || value === undefined || value === "") return "未提供";
  if (Array.isArray(value)) return value.length ? value.join("、") : "无";
  return String(value);
}
