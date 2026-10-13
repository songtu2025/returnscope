import { useEffect, useRef, useState } from "react";
import { InlineLoading, PageHeading } from "../../components/SharedUi";
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
        title="审计记录"
        action={
          <InlineLoading
            label="更新中…"
            compact
            active={state.loading && Boolean(state.data)}
          />
        }
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
