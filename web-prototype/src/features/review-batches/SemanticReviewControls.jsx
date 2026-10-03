import Button from "antd/es/button";
import Select from "antd/es/select";
import { Plus } from "@phosphor-icons/react";

/** @param {import("./semanticLedgerContracts").SemanticLedgerContext} context */
export function SemanticReviewControls(context) {
  const { coverageStatus, onCoverageStatus, setAdding } = context;
  return (
    <div className="semantic-review-controls">
      <label>
        观点覆盖判断
        <Select
          aria-label="观点覆盖判断"
          value={coverageStatus}
          onChange={onCoverageStatus}
          options={[
            { value: "complete", label: "已覆盖需要归类的观点" },
            { value: "has_omission", label: "存在遗漏观点" },
          ]}
        />
      </label>
      <Button icon={<Plus size={16} />} onClick={() => setAdding(true)}>
        补充遗漏观点
      </Button>
    </div>
  );
}
