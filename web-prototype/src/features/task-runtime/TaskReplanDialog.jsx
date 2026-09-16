import { useCallback, useEffect, useState } from "react";
import { WarningCircle } from "@phosphor-icons/react";

import { InlineLoading, Modal } from "../../components/SharedUi";
import { ExecutionPlanSummary } from "../task-planning/ExecutionPlanSummary";

export function TaskReplanDialog({ task, onClose, onPreflight, onSave }) {
  const [plan, setPlan] = useState(null);
  const [policy, setPolicy] = useState("");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const loadPlan = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const value = await onPreflight({ product_version_id: task.product_version_id });
      setPlan(value);
      setPolicy(value.blocked_count > 0 ? "" : "block_all");
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [onPreflight, task.product_version_id]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  const submit = async (event) => {
    event.preventDefault();
    if (!plan || !policy) return;
    setSaving(true);
    try {
      await onSave({
        product_version_id: task.product_version_id,
        expected_revision: task.revision,
        plan_hash: plan.plan_hash,
        unresolved_policy: policy,
        reason,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal eyebrow="任务恢复" title="重新预检并规划" onClose={onClose}>
      <form className="modal-form replan-form" onSubmit={submit}>
        {loading && <InlineLoading label="正在重新预检执行计划…" />}
        {error && (
          <div className="plan-state error" role="alert">
            <WarningCircle size={19} />
            <span>{error}</span>
            <button type="button" onClick={loadPlan}>
              重新预检
            </button>
          </div>
        )}
        {plan && (
          <ExecutionPlanSummary
            plan={plan}
            policy={policy}
            onPolicyChange={setPolicy}
          />
        )}
        <label>
          重新规划原因
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength="500"
            rows="3"
            placeholder="必填，说明本次重新规划依据"
            required
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            取消
          </button>
          <button
            className="primary-button"
            disabled={saving || loading || !plan || !policy || !reason.trim()}
          >
            {saving ? "正在更新…" : "提交新执行计划"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
