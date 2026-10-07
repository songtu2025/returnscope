import { writeAuditRoute } from "./auditLogPolicy";

/** @typedef {{draft: import("./auditLogPolicy").AuditFilters, setDraft: import("react").Dispatch<import("react").SetStateAction<import("./auditLogPolicy").AuditFilters>>, dateToRef: import("react").RefObject<HTMLInputElement | null>, dateRangeError: string}} FilterState */
/** @type {Array<{field: "actor_id" | "entity_type" | "entity_id" | "action", label: string, placeholder?: string}>} */
const TEXT_FILTERS = [
  { field: "actor_id", label: "操作人 ID" },
  { field: "entity_type", label: "对象类型", placeholder: "如 task" },
  { field: "entity_id", label: "对象 ID" },
  { field: "action", label: "动作" },
];

/** @param {FilterState & {route: import("./auditLogPolicy").AuditRoute}} props */
export function AuditLogFilter({ draft, setDraft, dateToRef, dateRangeError, route }) {
  return (
    <form
      className="audit-filter-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (dateRangeError) {
          dateToRef.current?.focus();
          return;
        }
        writeAuditRoute(route, { ...draft, page: "" });
      }}
    >
      {TEXT_FILTERS.map(({ field, label, placeholder }) => (
        <label key={field}>
          {label}
          <input
            value={draft[field]}
            placeholder={placeholder}
            onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
          />
        </label>
      ))}
      <AuditDateFilters
        draft={draft}
        setDraft={setDraft}
        dateToRef={dateToRef}
        dateRangeError={dateRangeError}
      />
      <button className="primary-button">筛选</button>
    </form>
  );
}

/** @param {FilterState} props */
function AuditDateFilters({ draft, setDraft, dateToRef, dateRangeError }) {
  return (
    <>
      <label>
        开始日期
        <input
          type="date"
          value={draft.date_from}
          onChange={(event) => setDraft({ ...draft, date_from: event.target.value })}
        />
      </label>
      <label>
        结束日期
        <input
          ref={dateToRef}
          type="date"
          aria-label="结束日期"
          value={draft.date_to}
          onChange={(event) => setDraft({ ...draft, date_to: event.target.value })}
          aria-invalid={Boolean(dateRangeError)}
          aria-describedby={dateRangeError ? "audit-date-to-error" : undefined}
        />
        {dateRangeError && (
          <small id="audit-date-to-error" className="audit-filter-error" role="alert">
            {dateRangeError}
          </small>
        )}
      </label>
    </>
  );
}
