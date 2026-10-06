import { formatNumber, formatPercent } from "../../lib/presentation";
import {
  SectionCard,
  EmptyAnalysis,
  DataBars,
  ChangeValue,
} from "./LegacyAnalysisDisplay";

/** @typedef {import("../../shared/api/legacyAnalysisContracts").AnalysisDiagnosis} AnalysisDiagnosis */
/** @typedef {NonNullable<AnalysisDiagnosis["priorities"]>[number]} Priority */
/** @typedef {{diagnosis: AnalysisDiagnosis, onFocusProblem: (code: string) => void}} DiagnosisProps */

/** @param {{row: Priority, focusCode: AnalysisDiagnosis["focus_code"], onFocusProblem: DiagnosisProps["onFocusProblem"]}} props */
function PriorityRow({ row, focusCode, onFocusProblem }) {
  return (
    <tr
      key={row.code}
      className={row.code === focusCode ? "is-selected" : ""}
      onClick={() => onFocusProblem(row.code)}
    >
      <td>
        <b>{row.name}</b>
        <small>{row.group}</small>
      </td>
      <td>{formatNumber(row.records)}</td>
      <td>{formatPercent(row.share)}</td>
      <td>
        <ChangeValue value={row.change_pp} />
      </td>
      <td>{formatNumber(row.sku_count)}</td>
      <td>{formatPercent(row.top_sku_share)}</td>
      <td>{formatNumber(row.multi_problem_records)}</td>
      <td>{formatNumber(row.review_records)}</td>
    </tr>
  );
}

/** @param {DiagnosisProps} props */
function PriorityTable({ diagnosis, onFocusProblem }) {
  return (
    <>
      {diagnosis.priorities?.length ? (
        <div className="analysis-table-scroll">
          <table className="analysis-table priority-table">
            <thead>
              <tr>
                <th>问题</th>
                <th>记录数</th>
                <th>退货构成</th>
                <th>30天变化</th>
                <th>影响SKU</th>
                <th>Top SKU占比</th>
                <th>多问题</th>
                <th>需复核</th>
              </tr>
            </thead>
            <tbody>
              {diagnosis.priorities.map((row) => (
                <PriorityRow
                  key={row.code}
                  row={row}
                  focusCode={diagnosis.focus_code}
                  onFocusProblem={onFocusProblem}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyAnalysis />
      )}
    </>
  );
}

/** @param {DiagnosisProps} props */
function ProblemPriority({ diagnosis, onFocusProblem }) {
  return (
    <SectionCard
      title="问题优先级"
      note="综合问题规模、近 30 天变化、影响商品范围与核查信号"
      action={
        <label className="compact-select">
          <span>诊断问题</span>
          <select
            value={diagnosis.focus_code ?? ""}
            onChange={(event) => onFocusProblem(event.target.value)}
          >
            {diagnosis.priorities?.map((item) => (
              <option key={item.code} value={item.code}>
                {item.name} · {formatNumber(item.records)} 条
              </option>
            ))}
          </select>
        </label>
      }
    >
      <PriorityTable diagnosis={diagnosis} onFocusProblem={onFocusProblem} />
    </SectionCard>
  );
}

/** @param {{focus: Priority}} props */
function DiagnosisSummary({ focus }) {
  return (
    <div className="diagnosis-summary">
      <div>
        <span>相关退货</span>
        <strong>{formatNumber(focus.records)}</strong>
        <small>占筛选退货 {formatPercent(focus.share)}</small>
      </div>
      <div>
        <span>近30天变化</span>
        <strong>{Number(focus.change_pp ?? 0).toFixed(1)} pp</strong>
        <small>与前30天相比</small>
      </div>
      <div>
        <span>影响 SKU</span>
        <strong>{formatNumber(focus.sku_count)}</strong>
        <small>Top SKU 占 {formatPercent(focus.top_sku_share)}</small>
      </div>
      <div>
        <span>需复核</span>
        <strong>{formatNumber(focus.review_records)}</strong>
        <small>含冲突与不确定结果</small>
      </div>
    </div>
  );
}

/** @param {{diagnosis: AnalysisDiagnosis}} props */
function DiagnosisComments({ diagnosis }) {
  return (
    <SectionCard
      title="评论证据"
      note={`展示 ${diagnosis.comments?.length ?? 0} 条去重评论`}
    >
      {diagnosis.comments?.length ? (
        <div className="evidence-list">
          {diagnosis.comments.map((item) => (
            <article key={item.classification_key}>
              <div>
                <span>{item.listing || "未匹配 Listing"}</span>
                <span>{item.sku || "无 SKU"}</span>
                <span>{item.reason || "无 Amazon 原因"}</span>
              </div>
              <p>{item.comment}</p>
              {item.evidence && <blockquote>{item.evidence}</blockquote>}
            </article>
          ))}
        </div>
      ) : (
        <EmptyAnalysis />
      )}
    </SectionCard>
  );
}

/** @param {{diagnosis: AnalysisDiagnosis, onFocusProblem: (code: string) => void}} props */
export function DiagnosisSection({ diagnosis, onFocusProblem }) {
  const focus = diagnosis.priorities?.find(
    (item) => item.code === diagnosis.focus_code,
  );
  return (
    <div className="analysis-section-stack">
      <ProblemPriority diagnosis={diagnosis} onFocusProblem={onFocusProblem} />

      {focus && <DiagnosisSummary focus={focus} />}
      <div className="analysis-grid analysis-grid-2">
        <SectionCard title="商品定位" note="提升度高于 1 表示该商品更集中出现此问题">
          <DataBars rows={diagnosis.product_locations} shareKey="share" />
        </SectionCard>
        <SectionCard title="Amazon 原因证据">
          <DataBars rows={diagnosis.reasons} />
        </SectionCard>
        <SectionCard title="部位定位">
          <DataBars rows={diagnosis.parts} />
        </SectionCard>
        <SectionCard title="问题共现" note="提升度高于 1 表示两个问题更常共同出现">
          <DataBars rows={diagnosis.pairs} />
        </SectionCard>
      </div>

      <DiagnosisComments diagnosis={diagnosis} />
    </div>
  );
}
