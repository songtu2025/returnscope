import { useState } from "react";
import { ACTION_LABELS, ENTITY_LABELS } from "./auditLogPresentation";
import { writeAuditRoute } from "./auditLogPolicy";

/** @typedef {{draft: import("./auditLogPolicy").AuditFilters, setDraft: import("react").Dispatch<import("react").SetStateAction<import("./auditLogPolicy").AuditFilters>>, dateToRef: import("react").RefObject<HTMLInputElement | null>, dateRangeError: string}} FilterState */
/** @param {FilterState & {route: import("./auditLogPolicy").AuditRoute}} props */
export function AuditLogFilter({ draft, setDraft, dateToRef, dateRangeError, route }) {
  const [advanced, setAdvanced] = useState(
    Boolean(
      draft.actor_id ||
      draft.entity_id ||
      (draft.action && !ACTION_LABELS[draft.action]) ||
      (draft.entity_type && !ENTITY_LABELS[draft.entity_type]),
    ),
  );
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
      <AuditSelect
        label="对象类型"
        field="entity_type"
        labels={ENTITY_LABELS}
        draft={draft}
        setDraft={setDraft}
      />
      <AuditSelect
        label="操作"
        field="action"
        labels={ACTION_LABELS}
        draft={draft}
        setDraft={setDraft}
      />
      <AuditDateFilters
        draft={draft}
        setDraft={setDraft}
        dateToRef={dateToRef}
        dateRangeError={dateRangeError}
      />
      <div className="audit-filter-actions">
        <button className="primary-button">筛选</button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => {
            const empty = {
              actor_id: "",
              entity_type: "",
              entity_id: "",
              action: "",
              date_from: "",
              date_to: "",
            };
            setDraft(empty);
            writeAuditRoute(route, { ...empty, page: "" });
          }}
        >
          重置
        </button>
        <button
          type="button"
          className="text-button"
          aria-expanded={advanced}
          aria-controls="audit-advanced-filters"
          onClick={() => setAdvanced(!advanced)}
        >
          高级筛选
        </button>
      </div>
      {advanced && (
        <div id="audit-advanced-filters" className="audit-advanced-filters">
          <label>
            对象类型代码
            <input
              value={draft.entity_type}
              onChange={(event) =>
                setDraft({ ...draft, entity_type: event.target.value })
              }
            />
          </label>
          <label>
            操作代码
            <input
              value={draft.action}
              onChange={(event) => setDraft({ ...draft, action: event.target.value })}
            />
          </label>
          <label>
            操作人 ID
            <input
              value={draft.actor_id}
              onChange={(event) => setDraft({ ...draft, actor_id: event.target.value })}
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
        </div>
      )}
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

/** @param {{label: string, field: "entity_type" | "action", labels: Record<string, string>, draft: FilterState["draft"], setDraft: FilterState["setDraft"]}} props */
function AuditSelect({ label, field, labels, draft, setDraft }) {
  return (
    <label>
      {label}
      <select
        value={draft[field]}
        onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
      >
        <option value="">全部{label}</option>
        {draft[field] && !labels[draft[field]] && (
          <option value={draft[field]}>{draft[field]}</option>
        )}
        {Object.entries(labels).map(([value, text]) => (
          <option key={value} value={value}>
            {text}
            {Object.values(labels).filter((label) => label === text).length > 1
              ? `（${value}）`
              : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
