import { useState } from "react";
import Button from "antd/es/button";

import { STATUS_LABELS } from "../../constants";
import { classNames, formatTime } from "../../lib/presentation";

const TASK_STAGES = ["准备数据", "Listing 分类", "发布分类版本", "任务结束"];
const TASK_STAGE_INDEX = {
  准备数据: 0,
  语义分析: 1,
  "Listing 分类": 1,
  生成结果: 2,
  发布分类版本: 2,
  模型服务异常: 1,
  分析完成: 3,
  任务结束: 3,
};

function taskStageLabel(stage) {
  if (/模型服务/.test(stage || "")) return "模型服务异常";
  if (TASK_STAGE_INDEX[stage] != null) return TASK_STAGES[TASK_STAGE_INDEX[stage]];
  if (/发布|生成结果/.test(stage || "")) return TASK_STAGES[2];
  if (/分类|语义/.test(stage || "")) return TASK_STAGES[1];
  if (/完成|结束|取消|失败/.test(stage || "")) return TASK_STAGES[3];
  return TASK_STAGES[0];
}

function eventListing(task, event) {
  const segmentId = event.data?.segment_id;
  if (!segmentId) return "";
  const segment = task.segments?.find((item) => item.id === segmentId);
  return segment?.scope?.listing ?? "";
}

export function TaskEventList({ task, events }) {
  const [visibleCount, setVisibleCount] = useState(100);
  const values = events.slice(-visibleCount).reverse();
  return (
    <div className="event-log">
      {values.length === 0 && <p className="muted-line">暂无运行动态。</p>}
      {values.map((event) => {
        const listing = eventListing(task, event);
        const message = listing
          ? event.message.replace(/^Listing\s*/, "")
          : event.message;
        return (
          <div key={event.id}>
            <time>{formatTime(event.created_at)}</time>
            <span className={classNames("event-dot", event.event_type)} />
            <p>
              <b>
                {listing
                  ? `${listing} · ${taskStageLabel(event.stage)}`
                  : taskStageLabel(event.stage)}
              </b>
              {message}
              {event.data?.before?.title && (
                <small>
                  原值：{event.data.before.title}
                  <br />
                  新值：{event.data.after.title}
                  <br />
                  原因：{event.data.note}
                </small>
              )}
              {event.data?.before?.status && (
                <small>
                  原状态：
                  {STATUS_LABELS[event.data.before.status] ?? event.data.before.status}
                  <br />
                  新状态：
                  {STATUS_LABELS[event.data.after.status] ?? event.data.after.status}
                  {event.data.note && (
                    <>
                      <br />
                      原因：{event.data.note}
                    </>
                  )}
                </small>
              )}
              {event.actor_name && <small>操作人：{event.actor_name}</small>}
            </p>
          </div>
        );
      })}
      {events.length > visibleCount && (
        <Button
          className="secondary-button"
          onClick={() => setVisibleCount((count) => count + 100)}
        >
          加载更早日志（已显示 {values.length} / {events.length} 条）
        </Button>
      )}
    </div>
  );
}
