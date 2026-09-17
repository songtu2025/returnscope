import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import {
  ClassificationValidationQuality,
  ValidationFactTrace,
} from "../src/features/classification-standards/ClassificationValidationQuality";
import { ClassificationStandardValidation } from "../src/features/classification-standards/ClassificationStandardValidation";

afterEach(cleanup);

test("v2策略说明中将自动检查项展示为中性差异", () => {
  render(
    <ClassificationValidationQuality
      run={{
        items: [],
        quality_gate: {
          policy: {
            version: "fact-reference-v2",
            min_reference_samples: 20,
            min_reference_coverage: 100,
            min_instance_match_rate: 95,
            max_duplicate_rate: 1,
            thresholds: {
              event_errors: 0,
              condition_errors: 0,
              subject_errors: 0,
              primary_errors: 0,
            },
          },
        },
      }}
    />,
  );
  expect(
    screen.getByText(
      /发布阻断零容忍项：事件关系差异、条件差异、责任主体差异、主因字段差异，均须为 0/,
    ),
  ).toBeVisible();
});

test("事实追踪以普通字段展示主因记录，不混淆使用者和责任主体", async () => {
  const user = userEvent.setup();
  render(
    <ValidationFactTrace
      result={{
        extracted_facts: [
          {
            fact_id: "primary",
            statement_type: "EXPERIENCE",
            actor_ref: "REVIEWER",
            product_ref: "CURRENT",
            subject: "PRODUCT",
            is_primary_reason: true,
            opinion: "内衬移位",
          },
          {
            fact_id: "service",
            statement_type: "EXPERIENCE",
            actor_ref: "REVIEWER",
            product_ref: "CURRENT",
            subject: "SERVICE",
            is_primary_reason: false,
            opinion: "客服解决问题",
          },
          { fact_id: "legacy", opinion: "旧记录" },
        ],
      }}
    />,
  );
  await user.click(screen.getByText("事实状态、对象与条件"));
  expect(screen.queryByText("主因", { selector: "strong" })).not.toBeInTheDocument();
  expect(screen.getByText(/主因字段 是/)).toBeVisible();
  expect(screen.getByText(/主因字段 否/)).toBeVisible();
  expect(screen.getByText(/主因字段 未记录/)).toBeVisible();
  expect(screen.getByText(/责任主体 PRODUCT/)).toBeVisible();
  expect(screen.getByText(/责任主体 SERVICE/)).toHaveTextContent("使用者 REVIEWER");
  expect(screen.getByText(/责任主体 未记录/)).toBeVisible();
});

test("旧参考缺少事件和主因列时明确显示未评估", () => {
  render(
    <ClassificationValidationQuality
      run={{
        items: [],
        summary: { reference_evaluation: { scope_sample_counts: {} } },
      }}
    />,
  );
  expect(
    screen.getByText(/事件 未评估；条件 未评估；责任主体 未评估；主因 未评估/),
  ).toBeVisible();
});

test("点击 Review 上传控件触发真实文件输入，选择后显示文件名并提交所选文件", async () => {
  const user = userEvent.setup();
  const onRun = vi.fn();
  render(
    <ClassificationStandardValidation
      draft={{ validation: { blocking: [] } }}
      sources={[]}
      runs={[]}
      sourceId="__review_file__"
      sampleSize={20}
      onRun={onRun}
    />,
  );
  const input = screen.getByLabelText("Review 表格");
  const clicked = vi.fn();
  input.addEventListener("click", clicked);
  await user.click(screen.getByText("选择 Review Excel"));
  expect(clicked).toHaveBeenCalledTimes(1);
  const file = new File(["synthetic workbook"], "独立验收.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  await user.upload(input, file);
  expect(screen.getByText("已选择：独立验收.xlsx")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "开始样本验证" }));
  expect(onRun).toHaveBeenCalledWith(file, "standard_version");
});

const run = {
  id: "quality-run",
  draft_revision: 2,
  status: "completed",
  is_current: true,
  source: {},
  sample_size: 20,
  processed_count: 20,
  model_names: [],
  error_count: 0,
  summary: {},
  quality_gate: {
    passed: false,
    status: "failed",
    blocking: ["事实状态错误=1，要求不超过 0"],
  },
  items: [
    {
      classification_key: "sample",
      source_row: 2,
      comment: "The child plans a trip.",
      reference: { ambiguous: true },
      reference_comparison: { draft: { statement_type_errors: 1 } },
      baseline: { status: "AUTO_APPROVED", semantic_units: [] },
      draft: {
        status: "NEEDS_REVIEW",
        semantic_units: [],
        review_reasons: ["需确认事实状态"],
        unknown_semantics: [{ opinion: "计划出行" }],
        extracted_facts: [
          {
            fact_id: "f1",
            statement_type: "INTENT",
            actor_ref: "child",
            product_ref: "current",
            condition: "next week",
            opinion: "计划使用",
            evidence_spans: [{ text: "The child plans a trip." }],
          },
        ],
        fact_mappings: [{ fact_id: "f1", label_codes: [] }],
      },
    },
  ],
};

test("质量问题按根因展开并显示事实状态和对象", async () => {
  const user = userEvent.setup();
  render(<ClassificationValidationQuality run={run} />);
  expect(screen.getByText("自动检查差异 · 1 条待检查")).toBeVisible();
  expect(
    screen.getByText(/不根据主因或次要标签自动判定正确、部分正确或错误/),
  ).toBeVisible();
  expect(screen.getByText("标签覆盖待核对 · 1 条待检查")).toBeVisible();
  expect(screen.getByText("人工歧义 · 1 条待检查")).toBeVisible();
  await user.click(screen.getByText("自动检查差异 · 1 条待检查"));
  await user.click(screen.getAllByText(/来源第 2 行/)[0]);
  expect(screen.getAllByText("事实状态差异：1")[0]).toBeVisible();
  await user.click(screen.getAllByText("事实状态、对象与条件")[0]);
  expect(screen.getAllByText("INTENT")[0]).toBeVisible();
  expect(screen.getAllByText(/使用者 child/)[0]).toBeVisible();
});

test("门槛失败时不能显示确认通过按钮，即使调用错误数为零", () => {
  render(
    <ClassificationStandardValidation
      draft={{ validation: { blocking: [] } }}
      sources={[]}
      runs={[run]}
      selectedRun={run}
      sourceId="source"
      sampleSize={20}
    />,
  );
  expect(
    screen.queryByRole("button", { name: "确认验证通过" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("自动质量门槛未通过，不能确认发布")).toBeVisible();
});

test("旧运行无自动评分时不显示虚假通过", () => {
  render(<ClassificationValidationQuality run={{ items: [] }} />);
  expect(screen.getByText("未配置自动质量门槛，保留人工确认流程")).toBeVisible();
});

test("显示对照与候选的实际执行效率，未记录指标不伪造为零", () => {
  render(
    <ClassificationValidationQuality
      run={{
        items: [],
        summary: {
          efficiency: {
            sides: {
              baseline: { review_count: 2, review_rate: 10 },
              draft: {
                model_calls: 112,
                average_model_calls: 5.6,
                total_tokens: 2856338,
                average_tokens: 142816.9,
                coverage_audit_count: 20,
                coverage_audit_rate: 100,
                review_count: 4,
                review_rate: 20,
              },
            },
          },
        },
      }}
    />,
  );
  const baselineRow = screen.getByText("对照").closest("tr");
  const draftRow = screen.getByText("候选").closest("tr");
  expect(baselineRow).toHaveTextContent("-- 次 · 平均 -- 次/条");
  expect(baselineRow).toHaveTextContent("10% · 2 条");
  expect(draftRow).toHaveTextContent("112 次 · 平均 5.6 次/条");
  expect(draftRow).toHaveTextContent("2,856,338 · 平均 142,816.9 Token/条");
  expect(draftRow).toHaveTextContent("100% · 20 次");
  expect(draftRow).toHaveTextContent("20% · 4 条");
});

test("参考确认留空移至非阻断记录，真实漏标和未覆盖语义仍保留", async () => {
  const user = userEvent.setup();
  const comparison = Object.fromEntries(
    [
      "duplicate_units",
      "extra_labels",
      "missing_labels",
      "direction_errors",
      "part_errors",
      "evidence_errors",
      "model_errors",
      "statement_type_errors",
      "actor_errors",
      "product_errors",
      "plan_confirmation_errors",
      "event_errors",
      "condition_errors",
      "subject_errors",
      "primary_errors",
    ].map((key) => [key, 0]),
  );
  const expected = {
    classification_key: "expected",
    comment: "Waterproofing is untested.",
    reference: {
      ambiguous: false,
      facts: [
        {
          expected_statement_type: "NOT_TESTED",
          label_codes: [],
          evidence: "Waterproofing is untested.",
        },
      ],
    },
    reference_comparison: { draft: comparison },
    draft: {
      status: "UNKNOWN_SEMANTIC",
      review_reasons: ["尚未测试"],
      unknown_semantics: [{ opinion: "未测试防水" }],
      extracted_facts: [
        {
          fact_id: "f",
          statement_type: "NOT_TESTED",
          opinion: "未测试防水",
          evidence_spans: [{ text: "Waterproofing is untested." }],
        },
      ],
      fact_mappings: [{ fact_id: "f", label_codes: [] }],
    },
  };
  const gap = {
    ...expected,
    classification_key: "gap",
    draft: {
      ...expected.draft,
      extracted_facts: expected.draft.extracted_facts.map((fact) => ({
        ...fact,
        statement_type: "EVALUATION",
      })),
    },
    reference: { ambiguous: false, facts: [] },
  };
  const missing = {
    ...expected,
    classification_key: "missing",
    reference_comparison: { draft: { ...comparison, missing_labels: 1 } },
  };
  render(
    <ClassificationValidationQuality
      run={{
        items: [expected, gap, missing],
        quality_gate: { status: "passed", passed: true },
      }}
    />,
  );
  expect(screen.getByText("自动检查差异 · 1 条待检查")).toBeVisible();
  expect(screen.getByText("标签覆盖待核对 · 2 条待检查")).toBeVisible();
  expect(screen.getByText("预期留空或人工关注（非阻断） · 1 条记录")).toBeVisible();
  await user.click(screen.getByText("自动检查差异 · 1 条待检查"));
  await user.click(screen.getAllByText(/来源第 .*Waterproofing is untested/)[0]);
  expect(screen.getAllByText("漏标实例：1")[0]).toBeVisible();
});
