/** @typedef {import("./analysisDashboardContracts").ConciseInsightReportContent} Content */
/** @typedef {import("./analysisDashboardContracts").InsightEvidenceCatalog} Catalog */

/** @param {{content: Content, catalog: Catalog}} props */
export function ConciseInsightBody({ content, catalog }) {
  const evidenceIds = [
    ...new Set(content.insights.flatMap((item) => item.evidence_ids)),
  ];
  return (
    <div className="concise-insight-body">
      <p className="concise-insight-judgment">{content.judgment}</p>
      <section aria-labelledby="concise-insight-heading">
        <h3 id="concise-insight-heading">核心洞察</h3>
        <ol className="concise-insight-list">
          {content.insights.map((item) => (
            <li key={item.id}>
              <h4>
                <a
                  href={`#concise-evidence-${item.id}`}
                  onClick={(event) => {
                    event.preventDefault();
                    const entry = document.getElementById(
                      `concise-evidence-${item.id}`,
                    );
                    const details = entry?.closest("details");
                    if (details) details.open = true;
                    entry?.scrollIntoView?.({ block: "nearest" });
                  }}
                >
                  {item.title}
                </a>
              </h4>
              <p>
                <strong>{item.fact}</strong> {item.meaning}
              </p>
            </li>
          ))}
        </ol>
      </section>
      {content.actions.length > 0 && (
        <section aria-labelledby="concise-actions-heading">
          <h3 id="concise-actions-heading">产品行动优先级</h3>
          <ul className="concise-insight-actions">
            {content.actions.map((item) => (
              <li key={item.id}>
                <h4>
                  <span>{item.priority}</span> {item.title}
                </h4>
                <p>{item.action}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      <p className="concise-insight-closing">{content.closing}</p>
      <details className="concise-insight-evidence">
        <summary>数据口径与完整证据</summary>
        <ul>
          {content.boundaries.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        <dl>
          {evidenceIds.map((id) => {
            const item = catalog[id];
            const insight = content.insights.find(
              (entry) => entry.evidence_ids[0] === id,
            );
            return item ? (
              <div key={id} id={insight && `concise-evidence-${insight.id}`}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
                {Array.isArray(item.data) &&
                  item.data.every(
                    (month) => month?.month && typeof month.total === "number",
                  ) && (
                    <dd>
                      {item.data
                        .map((month) => `${month.month} ${month.count}/${month.total}`)
                        .join("，")}
                    </dd>
                  )}
              </div>
            ) : null;
          })}
        </dl>
      </details>
    </div>
  );
}
