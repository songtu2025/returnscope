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
    <div className="verifiable-table-shell">
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
    </div>
  );
}

/** @param {{chapter: Chapter}} props */
function EvidenceChapter({ chapter }) {
  const [open, setOpen] = useState(false);
  const headingId = `report-chapter-${chapter.id}`;
  const evidenceId = `report-evidence-${chapter.id}`;
  return (
    <section className="verifiable-chapter" aria-labelledby={headingId}>
      <header className="verifiable-chapter-heading">
        <p className="verifiable-chapter-name">{chapter.name}</p>
        <h3 id={headingId} tabIndex={-1}>
          {chapter.title}
        </h3>
      </header>
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
      <p className="verifiable-explanation">{chapter.explanation}</p>
      <div className="verifiable-guidance">
        <div className="verifiable-boundary">
          <strong>判断边界</strong>
          <p>{chapter.boundary}</p>
        </div>
        <div className="verifiable-next-step">
          <strong>下一步行动</strong>
          <p>{chapter.action}</p>
        </div>
      </div>
      <div className="verifiable-chapter-actions">
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
      </div>
      <div className="verifiable-evidence" id={evidenceId} hidden={!open}>
        <header className="verifiable-evidence-heading">
          <h4>完整证据</h4>
          <p>对照分解、代表反馈与统计口径均冻结在本报告版本中。</p>
        </header>
        <section>
          <h5>对比分解</h5>
          <MetricsTable rows={chapter.breakdown} label={`${chapter.name}对比分解`} />
        </section>
        <section>
          <h5>代表反馈</h5>
          {chapter.records.length ? (
            chapter.records.map((record) => (
              <article key={record.record_id} className="verifiable-record">
                <blockquote>{record.excerpt}</blockquote>
                <dl>
                  <div>
                    <dt>反馈日期</dt>
                    <dd>{record.date || "--"}</dd>
                  </div>
                  <div>
                    <dt>商品</dt>
                    <dd>{record.product || "商品未确认"}</dd>
                  </div>
                  <div>
                    <dt>映射状态</dt>
                    <dd>
                      {record.mapping_status === "matched"
                        ? record.product
                          ? "已匹配"
                          : "已有匹配标记，缺商品名称"
                        : "未匹配"}
                    </dd>
                  </div>
                  <div>
                    <dt>复核状态</dt>
                    <dd>
                      {record.review_status === "review_required"
                        ? "待复核"
                        : record.review_status === "ready"
                          ? "就绪"
                          : "复核状态未提供"}
                    </dd>
                  </div>
                </dl>
                <p>
                  {record.reason} · 源行 {record.source_row ?? "--"} ·{" "}
                  <code>{record.record_id}</code>
                </p>
              </article>
            ))
          ) : (
            <p>当前章节没有冻结的代表记录。</p>
          )}
        </section>
        <section>
          <h5>统计口径</h5>
          <p>{chapter.definition}</p>
        </section>
        <section>
          <h5>源记录入口</h5>
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
        </section>
      </div>
    </section>
  );
}

/** @param {{content: Content, count?: number}} props */
export function VerifiableInsightBody({ content, count }) {
  return (
    <div className="verifiable-report">
      <section className="verifiable-summary" aria-labelledby="verifiable-summary">
        <header>
          <h3 id="verifiable-summary">决策摘要</h3>
          <p>{count ?? "--"} 条纳入反馈 · 结论仅代表当前反馈样本</p>
        </header>
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
          <strong>报告目录</strong>
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
              <div className="verifiable-table-shell">
                <table
                  className="verifiable-metrics verifiable-actions"
                  aria-label="产品行动优先级"
                >
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
              </div>
            </section>
          )}
          <details className="verifiable-chapter verifiable-report-boundaries">
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
