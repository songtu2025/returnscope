import { ArrowClockwise, ClockCounterClockwise } from "@phosphor-icons/react";
import { EmptyState, InlineLoading } from "../../components/SharedUi";
import { AuditLogEntries, AuditLogPagination } from "./AuditLogEntries";
import { PAGE_SIZE } from "./auditLogPolicy";

/** @param {{state: ReturnType<typeof import("./useAuditLogs").useAuditLogs>["state"], load: ReturnType<typeof import("./useAuditLogs").useAuditLogs>["load"], dateRangeError: string, page: number, route: import("./auditLogPolicy").AuditRoute}} props */
export function AuditLogResults({ state, load, dateRangeError, page, route }) {
  const total = Number(state.data?.total ?? 0);
  const pages = Math.max(Math.ceil(total / PAGE_SIZE), 1);
  return (
    <>
      {dateRangeError ? (
        <div className="plan-state error audit-error">
          <div>
            <b>日期范围有误</b>
            <p>请修正结束日期后重新筛选，当前审计结果已隐藏。</p>
          </div>
        </div>
      ) : state.loading ? (
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
          <AuditLogEntries items={state.data.items} />
          <AuditLogPagination total={total} page={page} pages={pages} route={route} />
        </>
      )}
    </>
  );
}
