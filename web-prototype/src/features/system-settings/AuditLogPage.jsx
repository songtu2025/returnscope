import { useEffect, useRef, useState } from "react";
import { PageHeading } from "../../components/SharedUi";
import { filtersFromRoute, getDateRangeError, numberParam } from "./auditLogPolicy";
import { AuditLogFilter } from "./AuditLogFilter";
import { AuditLogResults } from "./AuditLogResults";
import { useAuditLogs } from "./useAuditLogs";

/** @typedef {import("./auditLogPolicy").AuditRoute} AuditRoute */

/** @param {{route: AuditRoute}} props */
export function AuditLogPage({ route }) {
  const page = numberParam(route.query.page);
  const [draft, setDraft] = useState(() => filtersFromRoute(route));
  const dateToRef = useRef(/** @type {HTMLInputElement | null} */ (null));
  const dateRangeError = getDateRangeError(draft);

  useEffect(() => setDraft(filtersFromRoute(route)), [route]);

  const { state, load } = useAuditLogs(route, page);

  return (
    <div className="standard-page audit-page">
      <PageHeading
        eyebrow="系统治理"
        title="审计记录"
        description="按操作人、对象和日期追溯系统变更；敏感字段始终掩码。"
      />
      <section className="content-card audit-card">
        <AuditLogFilter
          draft={draft}
          setDraft={setDraft}
          dateToRef={dateToRef}
          dateRangeError={dateRangeError}
          route={route}
        />

        <AuditLogResults
          state={state}
          load={load}
          dateRangeError={dateRangeError}
          page={page}
          route={route}
        />
      </section>
    </div>
  );
}
