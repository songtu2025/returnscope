import { useState } from "react";
import { buildHash } from "../../app/hashRouter";

/** @typedef {import("./analysisDashboardContracts").ReportMetric} Metric */
/** @typedef {import("./analysisDashboardContracts").VerifiableChapter} Chapter */
/** @typedef {import("./analysisDashboardContracts").VerifiableInsightReportContent} Content */

/** @param {string} id */
function goToChapter(id) {
  const heading = document.getElementById(`report-chapter-${id}`);
  heading?.focus({ preventScroll: true });
  heading?.scrollIntoView?.({ block: "start" });
}

/** @param {{rows: Metric[], label: string}} props */
function MetricsTable({ rows, label }) {
  if (!rows.length) return <p>当前范围没有符合口径的数据。</p>;
  return (
    <table className="verifiable-metrics" aria-label={label}>
      <thead>
        <tr>
          <th scope="col">指标</th>
          <th scope="col">反馈数</th>
          <th scope="col">占比</th>
          <th scope="col">分母范围</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((item) => (
          <tr key={item.label}>
            <th scope="row">{item.label}</th>
            <td>
              {item.numerator} / {item.denominator} {item.unit}
            </td>
            <td>{item.percent == null ? "--" : `${item.percent.toFixed(1)}%`}</td>
            <td>{item.scope}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** @param {{chapter: Chapter}} props */
function EvidenceChapter({ chapter }) {
  const [open, setOpen] = useState(false);
  const headingId = `report-chapter-${chapter.id}`;
  const evidenceId = `report-evidence-${chapter.id}`;
  return (
    <section className="verifiable-chapter" aria-labelledby={headingId}>
      <p className="verifiable-chapter-name">{chapter.name}</p>
      <h3 id={headingId} tabIndex={-1}>
        {chapter.title}
      </h3>
      <MetricsTable rows={chapter.metrics} label={`${chapter.name}关键事实`} />
      {chapter.breakdown.length > 0 && (
        <ul className="verifiable-breakdown">
          {chapter.breakdown.map((row) => (
            <li key={row.label}>
              {row.label}{" "}
              <strong>
                {row.numerator}
                {chapter.id === "signals" ? ` / ${row.denominator}` : ""} 条
                {chapter.id === "signals" && row.percent != null
                  ? `（${row.percent.toFixed(1)}%）`
                  : ""}
              </strong>
            </li>
          ))}
        </ul>
      )}
      <p>{chapter.explanation}</p>
      <p className="verifiable-boundary">{chapter.boundary}</p>
      <p>
        <strong>下一步</strong> {chapter.action}
      </p>
      <button
        type="button"
        className="secondary-button"
        aria-expanded={open}
        aria-controls={evidenceId}
        onClick={() => setOpen(!open)}
      >
        {open ? "收起证据" : "核查证据"}
        <span className="sr-only">（{chapter.name}）</span>
      </button>
      <div className="verifiable-evidence" id={evidenceId} hidden={!open}>
        <h4>对比分解</h4>
        <MetricsTable rows={chapter.breakdown} label={`${chapter.name}对比分解`} />
        <h4>代表反馈</h4>
        {chapter.records.length ? (
          chapter.records.map((record) => (
            <div key={record.record_id} className="verifiable-record">
              <blockquote>{record.excerpt}</blockquote>
              <p>
                {record.date || "--"} · {record.product || "商品未确认"} ·{" "}
                {record.mapping_status === "matched"
                  ? record.product
                    ? "已匹配"
                    : "已有匹配标记，缺商品名称"
                  : "未匹配"}{" "}
                ·{" "}
                {record.review_status === "review_required"
                  ? "待复核"
                  : record.review_status === "ready"
                    ? "就绪"
                    : "复核状态未提供"}
              </p>
              <p>
                {record.reason} · 源行 {record.source_row ?? "--"} ·{" "}
                <code>{record.record_id}</code>
              </p>
            </div>
          ))
        ) : (
          <p>当前章节没有冻结的代表记录。</p>
        )}
        <h4>统计口径</h4>
        <p>{chapter.definition}</p>
        <h4>源记录入口</h4>
        {chapter.records.length ? (
          <ul>
            {chapter.records.map((record) => (
              <li key={record.record_id}>
                {record.source_record_id ? (
                  <a
                    target="_blank"
                    rel="noopener"
                    href={buildHash("classification-results", {
                      result_version_id: record.result_version_id,
                      feedback_source_record_id: record.source_record_id,
                    })}
                  >
                    查看分类反馈组（源行 {record.source_row ?? "--"}，新标签页）
                  </a>
                ) : (
                  <>
                    源行 {record.source_row ?? "--"}{" "}
                    未提供可定位的源记录标识，可核对上方冻结摘录与记录 ID。
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p>当前章节未绑定源记录。</p>
        )}
      </div>
    </section>
  );
}

/** @param {{content: Content, count?: number}} props */
export function VerifiableInsightBody({ content, count }) {
  return (
    <div className="verifiable-report">
      <section className="verifiable-summary" aria-labelledby="verifiable-summary">
        <p>
          <strong>{count ?? "--"} 条反馈 · 仅代表反馈样本</strong>
        </p>
        <h3 id="verifiable-summary">决策摘要</h3>
        <dl>
          {content.summary.map((item) => (
            <div key={item.label}>
              <dt>{item.label}</dt>
              <dd>{item.text}</dd>
            </div>
          ))}
        </dl>
      </section>
      <div className="verifiable-grid">
        <nav aria-label="报告章节" className="verifiable-nav">
          {content.chapters.map((chapter) => (
            <button
              type="button"
              key={chapter.id}
              onClick={() => goToChapter(chapter.id)}
            >
              {chapter.name}
            </button>
          ))}
        </nav>
        <div className="verifiable-main">
          {content.chapters.map((chapter) => (
            <EvidenceChapter chapter={chapter} key={chapter.id} />
          ))}
          {content.actions.length > 0 && (
            <section className="verifiable-chapter">
              <h3>产品行动优先级</h3>
              <table className="verifiable-metrics verifiable-actions">
                <thead>
                  <tr>
                    <th scope="col">优先级</th>
                    <th scope="col">动作与证据</th>
                    <th scope="col">预期产出</th>
                    <th scope="col">下一步决策</th>
                  </tr>
                </thead>
                <tbody>
                  {content.actions.map((entry) => {
                    const chapter = content.chapters.find(
                      ({ id }) => id === entry.chapter_id,
                    );
                    return (
                      <tr key={entry.chapter_id}>
                        <th scope="row">{entry.priority}</th>
                        <td>
                          {chapter?.action}
                          <br />
                          <button
                            type="button"
                            onClick={() => goToChapter(entry.chapter_id)}
                          >
                            {chapter?.name}
                          </button>
                        </td>
                        <td>{entry.output}</td>
                        <td>{entry.decision}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          )}
          <details className="verifiable-chapter">
            <summary>报告数据范围与共同口径</summary>
            <ul>
              {content.boundaries.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
        </div>
      </div>
    </div>
  );
}
