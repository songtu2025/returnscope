import { useState } from "react";
import Button from "antd/es/button";
import Checkbox from "antd/es/checkbox";
import { CheckCircle, SpinnerGap } from "@phosphor-icons/react";

export function ClassificationStandardValidationApproval({
  run,
  isNew,
  busy,
  onApprove,
}) {
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  if (run.approved_at && run.quality_gate?.passed !== false) {
    return (
      <div className="standard-validation-approval ready">
        <CheckCircle size={20} weight="fill" aria-hidden="true" />
        <div>
          <b>{isNew ? "验证结果已人工确认" : "验证差异已人工确认"}</b>
          <span>
            {run.approved_by_name || "当前用户"}：{run.approval_note}
          </span>
        </div>
      </div>
    );
  }
  if (
    run.quality_gate?.passed === false ||
    !run.is_current ||
    Number(run.error_count) > 0 ||
    (run.source.comparison_type && run.source.comparison_type !== "standard_version")
  )
    return null;
  return (
    <div className="standard-validation-approval">
      <div>
        <b>人工审阅确认</b>
        <span>
          请检查{isNew ? "样本分类" : "标签变化"}
          、覆盖率、未知语义和评论证据，再确认本次验证。
        </span>
      </div>
      <Checkbox
        className="standard-validation-confirmation"
        checked={confirmed}
        onChange={(event) => setConfirmed(event.target.checked)}
      >
        {isNew ? "我已审阅样本分类和证据" : "我已审阅新旧版本差异和样本证据"}
      </Checkbox>
      <label>
        验证结论
        <textarea
          rows={2}
          value={note}
          placeholder="例如：新增标签边界清楚，未知语义均已检查"
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <Button
        htmlType="button"
        type="primary"
        className="primary-button"
        disabled={busy || !confirmed || !note.trim()}
        icon={
          busy ? (
            <SpinnerGap size={16} className="spin" aria-hidden="true" />
          ) : (
            <CheckCircle size={16} aria-hidden="true" />
          )
        }
        onClick={() => onApprove(run.id, note.trim())}
      >
        {busy ? "确认中" : "确认验证通过"}
      </Button>
    </div>
  );
}
