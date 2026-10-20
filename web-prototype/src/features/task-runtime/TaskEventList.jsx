import { useEffect, useState } from "react";
import Button from "antd/es/button";

import { STATUS_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";
import { SEGMENT_STATUS_LABELS } from "./segmentBoardRowPolicy";
import { TaskEventFilters } from "./TaskEventFilters";

/** @typedef {import("./taskRuntimeContracts").AnalysisTask} AnalysisTask */
/** @typedef {import("./taskRuntimeContracts").TaskEvent} TaskEvent */
/** @typedef {{key: string, label: string, store?: string}} LogListingTarget */

const TASK_STAGES = ["准备数据", "Listing 分类", "生成分类结果", "任务结束"];
/** @type {Record<string, string>} */
const EVENT_STATUS_LABELS = { ...SEGMENT_STATUS_LABELS, ...STATUS_LABELS };
/** @type {Record<string, number>} */
const TASK_STAGE_INDEX = {
  准备数据: 0,
  语义分析: 1,
  "Listing 分类": 1,
  生成结果: 2,
  生成分类结果: 2,
  发布分类版本: 2,
  模型服务异常: 1,
  分析完成: 3,
  任务结束: 3,
};

/** @param {string} stage */
function taskStageLabel(stage) {
  if (/模型服务/.test(stage || "")) return "模型服务异常";
  if (TASK_STAGE_INDEX[stage] != null) return TASK_STAGES[TASK_STAGE_INDEX[stage]];
  if (/发布|生成结果/.test(stage || "")) return TASK_STAGES[2];
  if (/分类|语义/.test(stage || "")) return TASK_STAGES[1];
  if (/完成|结束|取消|失败/.test(stage || "")) return TASK_STAGES[3];
  return TASK_STAGES[0];
}

/** @param {AnalysisTask} task @param {TaskEvent} event */
function eventTarget(task, event) {
  const { segment_id = "", segment_key = "" } = event.data ?? {};
  const segments = task.segments ?? [];
  const segment =
    segments.find((item) => item.id === segment_id) ??
    segments.find((item) => item.segment_key === segment_key);
  const { id, segment_key: knownKey, scope = {} } = segment ?? {};
  const key = knownKey || id || segment_key || segment_id;
  return { key, label: scope.listing || key, store: scope.store };
}

/** @param {string | undefined} status */
function eventStatusLabel(status) {
  if (!status) return "—";
  const pendingStatus = status.replace(/_requested$/, "_pending");
  return EVENT_STATUS_LABELS[pendingStatus] ?? status;
}

/** @param {{event: TaskEvent, listing: string}} props */
function TaskEventRow({ event, listing }) {
  const { data = {} } = event;
  const { before = {}, after = {}, before_status, after_status, note } = data;
  const beforeStatus = before.status ?? before_status;
  const afterStatus = after.status ?? after_status;
  const message = listing ? event.message.replace(/^Listing\s*/, "") : event.message;
  return (
    <div>
      <time>{formatTime(event.created_at)}</time>
      <span className={classNames("event-dot", event.event_type)} />
      <p>
        <b>
          {listing
            ? `${listing} · ${taskStageLabel(event.stage)}`
            : taskStageLabel(event.stage)}
        </b>
        {message}
        {before.title && (
          <small>
            原值：{before.title}
            <br />
            新值：{after.title}
          </small>
        )}
        {(beforeStatus || afterStatus) && (
          <small>
            原状态：{eventStatusLabel(beforeStatus)}
            <br />
            新状态：{eventStatusLabel(afterStatus)}
          </small>
        )}
        {note && <small>原因：{note}</small>}
        {event.actor_name && <small>操作人：{event.actor_name}</small>}
      </p>
    </div>
  );
}

/** @param {{task: AnalysisTask, events: TaskEvent[], filterable?: boolean, focusListing?: LogListingTarget | null}} props */
export function TaskEventList({ task, events, filterable = false, focusListing }) {
  const [visibleCount, setVisibleCount] = useState(100);
  const [filters, setFilters] = useState({ query: "", listing: "", type: "" });
  useEffect(() => {
    if (!focusListing) return;
    setFilters({ query: "", listing: focusListing.key, type: "" });
    setVisibleCount(100);
  }, [focusListing]);
  const keyword = filters.query.trim().toLowerCase();
  const filtered = Boolean(keyword || filters.listing || filters.type);
  const entries = events.map((event) => ({ event, target: eventTarget(task, event) }));
  const matches = entries.filter(({ event, target }) => {
    if (filters.listing && target.key !== filters.listing) return false;
    if (filters.type && event.event_type !== filters.type) return false;
    if (!keyword) return true;
    const {
      before = {},
      after = {},
      before_status,
      after_status,
      note,
    } = event.data ?? {};
    const text = [
      target.label,
      target.key,
      target.store,
      taskStageLabel(event.stage),
      event.message,
      event.actor_name,
      note,
      before.title,
      after.title,
      eventStatusLabel(before.status ?? before_status),
      eventStatusLabel(after.status ?? after_status),
    ]
      .join(" ")
      .toLowerCase();
    return text.includes(keyword);
  });
  const values = matches.slice(-visibleCount).reverse();
  return (
    <>
      {filterable && (
        <TaskEventFilters
          filters={filters}
          listings={[
            ...new Map(
              [...(focusListing ? [{ target: focusListing }] : []), ...entries]
                .filter(({ target }) => target.key)
                .map(({ target }) => [target.key, target]),
            ).values(),
          ]}
          types={[...new Set(events.map((event) => event.event_type).filter(Boolean))]}
          onChange={(next) => {
            setFilters(next);
            setVisibleCount(100);
          }}
          filtered={filtered}
          count={matches.length}
          total={events.length}
        />
      )}
      <div className="event-log">
        {values.length === 0 && (
          <p className="muted-line">
            {filtered ? "没有匹配的日志。" : "暂无运行动态。"}
          </p>
        )}
        {values.map(({ event, target }) => (
          <TaskEventRow key={event.id} event={event} listing={target.label} />
        ))}
        {matches.length > visibleCount && (
          <Button
            className="secondary-button"
            onClick={() => setVisibleCount((count) => count + 100)}
          >
            加载更早日志（已显示 {values.length} / {matches.length} 条）
          </Button>
        )}
      </div>
    </>
  );
}
