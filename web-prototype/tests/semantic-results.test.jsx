import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import { SemanticResultPanel } from "../src/features/classification-results/SemanticResultPanel";
import {
  semanticConclusions,
  semanticRecordStatus,
  semanticUnknownGroups,
} from "../src/features/classification-results/semanticResultPresentation";
import { ReturnReasonInsights } from "../src/features/analysis-dashboards/ReturnReasonInsights";

const mixedRecord = {
  comment_summary_status: "MIXED",
  comment_conclusions: [
    {
      id: "TOUCHSCREEN",
      topic_name: "触屏表现",
      topic_path: ["功能", "触屏表现"],
      status: "MIXED",
      summary: "基础操作可用，但精确打字受限",
      supporting_fact_ids: ["F1", "F2"],
    },
  ],
  semantic_relations: [
    {
      relation_type: "MIXED",
      fact_ids: ["F1", "F2"],
      label_codes: ["TOUCH_WORKS", "TOUCH_LIMITED"],
      reason: "基础操作与精确输入的适用范围不同",
    },
  ],
  atomic_facts: [
    {
      fact_id: "F1",
      label_code: "TOUCH_WORKS",
      full_label_path: ["功能", "触屏表现", "触屏可用"],
      evaluation_direction: "POSITIVE",
      assertion_status: "AFFIRMED",
      condition: { device: "手机" },
      operation: "滑动、点击",
      part: "FINGER",
      actor_ref: "REVIEWER",
      evidence_source: "BODY",
      evidence: "Swiping and tapping work well.",
    },
    {
      fact_id: "F2",
      label_code: "TOUCH_LIMITED",
      full_label_path: ["功能", "触屏表现", "精确操作受限"],
      evaluation_direction: "NEGATIVE",
      assertion_status: "AFFIRMED",
      condition: { device: "手机" },
      operation: "精确打字",
      part: "FINGER",
      actor_ref: "REVIEWER",
      evidence_source: "BODY",
      evidence: "Typing is trickier and less accurate.",
    },
  ],
  classification: {
    comment_summary: { status: "POSITIVE", fact_ids: ["F1"] },
    semantic_units: [
      {
        fact_id: "F1",
        label_code: "TOUCH_WORKS",
        full_label_path: ["功能", "触屏表现", "触屏可用"],
        evaluation_direction: "POSITIVE",
        assertion_status: "AFFIRMED",
        condition: { device: "手机" },
        operation: "滑动、点击",
        part: "FINGER",
        actor_ref: "REVIEWER",
        evidence_source: "BODY",
        evidence: "Swiping and tapping work well.",
      },
      {
        fact_id: "F2",
        label_code: "TOUCH_LIMITED",
        full_label_path: ["功能", "触屏表现", "精确操作受限"],
        evaluation_direction: "NEGATIVE",
        assertion_status: "AFFIRMED",
        condition: { device: "手机" },
        operation: "精确打字",
        part: "FINGER",
        actor_ref: "REVIEWER",
        evidence_source: "BODY",
        evidence: "Typing is trickier and less accurate.",
      },
    ],
  },
};

describe("评论级语义呈现", () => {
  test("按主题显示混合结论并展开完整原子事实", async () => {
    const { container } = render(<SemanticResultPanel record={mixedRecord} />);

    expect(container.querySelectorAll(".semantic-label-group")).toHaveLength(2);
    expect(screen.getAllByText("混合表现")).toHaveLength(2);
    expect(screen.getByText("基础操作可用，但精确打字受限")).toBeVisible();
    expect(screen.getByText("功能 → 触屏表现 → 触屏可用")).toBeVisible();
    expect(screen.getByText("功能 → 触屏表现 → 精确操作受限")).toBeVisible();
    expect(screen.getByText("F1")).toBeVisible();
    expect(screen.getByText("滑动、点击", { exact: false })).toBeVisible();
    expect(screen.getAllByText("精确打字", { exact: false })).toHaveLength(2);
    expect(screen.getAllByText("已确认")).toHaveLength(2);
    expect(
      screen.getByText("Typing is trickier and less accurate.", { exact: false }),
    ).toBeVisible();
    expect(screen.getByRole("region", { name: "观点关系" })).toBeVisible();
    expect(screen.getByText("基础操作与精确输入的适用范围不同")).toBeVisible();
  });

  test("无 ID 的接口镜像只展示一次事实和证据", () => {
    const fact = {
      label_code: "SIZE_SMALL",
      label_path: ["尺码与适配", "偏小"],
      opinion: "尺码偏小",
      sentiment: "NEGATIVE",
      evidence: "The size is too small.",
    };
    const record = {
      atomic_facts: [fact],
      classification: { semantic_units: [{ ...fact }] },
    };

    expect(semanticConclusions(record)[0].facts).toHaveLength(1);
    const { container } = render(<SemanticResultPanel record={record} />);
    const view = within(container);
    const group = view.getByRole("region", { name: "尺码与适配 → 偏小" });
    expect(view.getByText("1 个标签 · 1 条事实")).toBeVisible();
    expect(view.getAllByText("尺码与适配")).toHaveLength(1);
    expect(
      within(group).getByText("The size is too small.", { exact: false }),
    ).toBeVisible();
    expect(group.querySelectorAll("blockquote")).toHaveLength(1);
  });

  test("同标签的两条真实事实合并展示但保留两处证据", () => {
    const facts = [
      {
        label_code: "SIZE_SMALL",
        label_path: ["尺码与适配", "偏小"],
        opinion: "手指处偏短",
        sentiment: "NEGATIVE",
        evidence: "The fingers are too short.",
      },
      {
        label_code: "SIZE_SMALL",
        label_path: ["尺码与适配", "偏小"],
        opinion: "掌部也偏紧",
        sentiment: "NEGATIVE",
        evidence: "The palm feels too tight.",
      },
    ];
    const record = {
      atomic_facts: facts,
      classification: { semantic_units: facts.map((fact) => ({ ...fact })) },
    };

    expect(semanticConclusions(record)[0].facts).toHaveLength(2);
    const { container } = render(<SemanticResultPanel record={record} />);
    const view = within(container);
    const group = view.getByRole("region", { name: "尺码与适配 → 偏小" });
    expect(view.getByText("1 个标签 · 2 条事实")).toBeVisible();
    expect(group.querySelectorAll("blockquote")).toHaveLength(2);
    expect(
      within(group).getByText("The fingers are too short.", { exact: false }),
    ).toBeVisible();
    expect(
      within(group).getByText("The palm feels too tight.", { exact: false }),
    ).toBeVisible();
  });

  test("相同语义事实只显示一张卡片，重复证据只显示一次", () => {
    const fact = {
      label_code: "BUYER_NO_NEED",
      label_path: ["买家原因", "买家自身原因", "不需要"],
      opinion: "My needs changed",
      evaluation_direction: "NEUTRAL",
      assertion_status: "EVALUATION",
      subject: "BUYER_REASON",
      evidence_source: "COMMENT",
      evidence: "My needs changed",
    };
    const record = {
      atomic_facts: [
        { ...fact, fact_id: "F1" },
        { ...fact, fact_id: "F2" },
      ],
    };

    const { container } = render(<SemanticResultPanel record={record} />);
    const group = within(container).getByRole("region", {
      name: "买家原因 → 买家自身原因 → 不需要",
    });
    expect(group.querySelectorAll(".semantic-fact-card")).toHaveLength(1);
    expect(group.querySelectorAll("blockquote")).toHaveLength(1);
    expect(within(group).getByText("F1、F2")).toBeVisible();
    expect(within(container).getByText("1 个标签 · 1 条事实")).toBeVisible();
  });

  test("相同语义事实的不同证据合并在一张卡片内", () => {
    const fact = {
      label_code: "BUYER_NO_NEED",
      label_path: ["买家原因", "买家自身原因", "不需要"],
      opinion: "需求已改变",
      evaluation_direction: "NEUTRAL",
      assertion_status: "EVALUATION",
    };
    const record = {
      atomic_facts: [
        { ...fact, fact_id: "F1", evidence: "My needs changed." },
        { ...fact, fact_id: "F2", evidence: "I no longer need it." },
      ],
    };

    const { container } = render(<SemanticResultPanel record={record} />);
    const group = within(container).getByRole("region", {
      name: "买家原因 → 买家自身原因 → 不需要",
    });
    expect(group.querySelectorAll(".semantic-fact-card")).toHaveLength(1);
    expect(group.querySelectorAll("blockquote")).toHaveLength(2);
    expect(
      within(group).getByText("My needs changed.", { exact: false }),
    ).toBeVisible();
    expect(
      within(group).getByText("I no longer need it.", { exact: false }),
    ).toBeVisible();
  });

  test("相同标签和中文事实但作用域不同仍保留两张卡片", () => {
    const fact = {
      label_code: "FIT_SMALL",
      label_path: ["尺码与适配", "偏小"],
      opinion: "穿着偏小",
      evaluation_direction: "NEGATIVE",
      assertion_status: "EVALUATION",
    };
    const record = {
      atomic_facts: [
        { ...fact, fact_id: "F1", variant_ref: "SIZE_M", evidence: "M is small." },
        { ...fact, fact_id: "F2", variant_ref: "SIZE_L", evidence: "L is small." },
      ],
    };

    const { container } = render(<SemanticResultPanel record={record} />);
    const group = within(container).getByRole("region", {
      name: "尺码与适配 → 偏小",
    });
    expect(group.querySelectorAll(".semantic-fact-card")).toHaveLength(2);
    expect(group.querySelectorAll("blockquote")).toHaveLength(2);
  });

  test("同标签正负评价合并到标签区块但各自方向与证据不丢失", () => {
    const record = {
      classification: {
        semantic_units: [
          {
            label_code: "FIT",
            label_path: ["尺码与适配", "贴合度"],
            sentiment: "POSITIVE",
            operation: "日常佩戴",
            evidence: "It fits well for daily use.",
          },
          {
            label_code: "FIT",
            label_path: ["尺码与适配", "贴合度"],
            sentiment: "NEGATIVE",
            operation: "运动时佩戴",
            evidence: "It feels loose while running.",
          },
        ],
      },
    };

    expect(semanticConclusions(record)[0].status).toBe("MIXED");
    const { container } = render(<SemanticResultPanel record={record} />);
    const group = within(container).getByRole("region", {
      name: "尺码与适配 → 贴合度",
    });
    expect(group.querySelectorAll("blockquote")).toHaveLength(2);
    expect(within(group).getByText("正向")).toBeVisible();
    expect(within(group).getByText("负向")).toBeVisible();
    expect(within(group).getByText("日常佩戴", { exact: false })).toBeVisible();
    expect(within(group).getByText("运动时佩戴", { exact: false })).toBeVisible();
  });

  test("旧结果缺少条件时不会把正负并存误称为有边界的混合表现", () => {
    const record = {
      classification: {
        semantic_units: [
          {
            label_code: "TOUCH_GOOD",
            label_path: ["触屏", "触屏灵敏"],
            sentiment: "POSITIVE",
            evidence: "Touch works.",
          },
          {
            label_code: "TOUCH_BAD",
            label_path: ["触屏", "触屏不灵敏"],
            sentiment: "NEGATIVE",
            evidence: "Typing is difficult.",
          },
        ],
      },
    };

    expect(semanticRecordStatus(record)).toBe("CONFLICT");
    expect(semanticConclusions(record)[0].status).toBe("CONFLICT");
    const { container } = render(<SemanticResultPanel record={record} />);
    const view = within(container);
    expect(view.getAllByText("疑似冲突")).toHaveLength(2);
    expect(view.getByText(/旧结果兼容视图/)).toBeVisible();
  });

  test("旧结果存在明确不同操作时归为混合表现", () => {
    const record = {
      classification: {
        semantic_units: [
          {
            label_path: ["功能", "触屏", "可用"],
            sentiment: "POSITIVE",
            operation: "滑动",
          },
          {
            label_path: ["功能", "触屏", "受限"],
            sentiment: "NEGATIVE",
            operation: "打字",
          },
        ],
      },
    };
    expect(semanticConclusions(record)[0].status).toBe("MIXED");
  });

  test("优先按维度裁决展示完整作用域和标签路径", async () => {
    const record = {
      classification: {
        dimension_decisions: [
          {
            parent_code: "WATERPROOF",
            verdict_label_code: "WATERPROOF_LIGHT_RAIN",
            supporting_fact_ids: ["F1"],
            context_fact_ids: [],
            reason: "小雨条件下保持干燥",
            scope: {
              source_ref: "REVIEWER",
              experiencer_ref: "REVIEWER",
              product_ref: "CURRENT",
              variant_ref: "SIZE_M",
              event_ref: "USE_1",
              reference_basis: "BARE_USE",
              part: "WHOLE_PRODUCT",
              operation: "户外步行",
              condition: "小雨",
            },
          },
          {
            parent_code: "WATERPROOF",
            verdict_label_code: "NOT_WATERPROOF_HEAVY_RAIN",
            supporting_fact_ids: ["F2"],
            context_fact_ids: [],
            reason: "大雨条件下出现渗水",
            scope: {
              source_ref: "REVIEWER",
              experiencer_ref: "REVIEWER",
              product_ref: "CURRENT",
              variant_ref: "SIZE_M",
              event_ref: "USE_2",
              reference_basis: "BARE_USE",
              part: "WHOLE_PRODUCT",
              operation: "户外步行",
              condition: "大雨",
            },
          },
        ],
        semantic_units: [
          {
            fact_id: "F1",
            label_code: "WATERPROOF_LIGHT_RAIN",
            label_path: ["性能", "防水性", "小雨防水"],
            sentiment: "POSITIVE",
            assertion: "AFFIRMED",
            evidence: "Stayed dry in light rain.",
            evidence_source: "BODY",
          },
          {
            fact_id: "F2",
            label_code: "NOT_WATERPROOF_HEAVY_RAIN",
            label_path: ["性能", "防水性", "大雨不防水"],
            sentiment: "NEGATIVE",
            assertion: "AFFIRMED",
            evidence: "Water came through in heavy rain.",
            evidence_source: "BODY",
          },
        ],
      },
    };

    expect(semanticConclusions(record)[0].status).toBe("MIXED");
    const { container } = render(<SemanticResultPanel record={record} />);
    const view = within(container);
    expect(view.getAllByText("混合表现")).toHaveLength(2);
    expect(view.getByText("性能 → 防水性 → 小雨防水")).toBeVisible();
    expect(view.getByText("性能 → 防水性 → 大雨不防水")).toBeVisible();
    expect(view.getAllByText("评论者 / 当前商品 / SIZE_M")).toHaveLength(2);
    expect(view.getByText("户外步行 / 小雨 / USE_1")).toBeVisible();
    expect(view.getByText("户外步行 / 大雨 / USE_2")).toBeVisible();
    expect(view.getAllByText("评论者 / 裸手使用")).toHaveLength(2);
    expect(view.getAllByText("商品整体")).toHaveLength(2);
    expect(view.getByText(/Stayed dry in light rain/)).toBeVisible();
  });

  test("每个标签就近展示中文事实、证据、作用域、因果和判定理由", () => {
    const record = {
      classification: {
        extracted_facts: [
          {
            fact_id: "F1",
            subject: "PRODUCT",
            opinion: "触屏只适合简单点击",
            part: "FINGER",
            operation: "简单点击",
            condition: "佩戴手套操作手机",
            source_ref: "REVIEWER",
            experiencer_ref: "REVIEWER",
            product_ref: "CURRENT",
            variant_ref: "UNSPECIFIED",
            event_ref: "USE_1",
            reference_basis: "MARKET_NORM",
            statement_type: "EXPERIENCE",
            sentiment: "NEGATIVE",
            evidence_spans: [{ text: "Only simple taps work.", source: "BODY" }],
          },
        ],
        semantic_units: [
          {
            fact_id: "F1",
            label_code: "TOUCH_OTHER",
            label_path: ["功能", "触屏表现", "其他"],
            opinion: "触屏只适合简单点击",
            sentiment: "NEGATIVE",
            statement_type: "EXPERIENCE",
            evidence: "Only simple taps work.",
            evidence_source: "BODY",
          },
        ],
        fact_mappings: [
          {
            fact_id: "F1",
            reason: "现有末端标签未覆盖简单操作可用但精细操作不足",
            relation_type: "CAUSED_BY",
            related_fact_ids: ["F2"],
          },
        ],
      },
    };

    const { container } = render(<SemanticResultPanel record={record} />);
    const view = within(container);

    expect(view.getByText("功能 → 触屏表现 → 其他")).toBeVisible();
    expect(view.getAllByText("触屏只适合简单点击")).toHaveLength(2);
    expect(view.getByText("当前商品 / 手指")).toBeVisible();
    expect(view.getByText("简单点击 / 佩戴手套操作手机 / USE_1")).toBeVisible();
    expect(view.getByText("实际体验")).toBeVisible();
    expect(view.getByText("由关联事实导致：F2")).toBeVisible();
    expect(
      view.getByText("现有末端标签未覆盖简单操作可用但精细操作不足"),
    ).toBeVisible();
    expect(view.getByText(/映射说明：现有末端标签未覆盖/)).toBeVisible();
    expect(view.getByText(/Only simple taps work/)).toBeVisible();
    expect(view.getByText("“其他”具体内容")).toBeVisible();
  });

  test("仅完整作用域相同的相反结论才标记为冲突", () => {
    const facts = [
      {
        label_path: ["功能", "触屏", "灵敏"],
        sentiment: "POSITIVE",
        source_ref: "REVIEWER",
        experiencer_ref: "REVIEWER",
        product_ref: "CURRENT",
        variant_ref: "SIZE_M",
        event_ref: "USE_1",
        reference_basis: "MARKET_NORM",
        part: "FINGER",
        operation: "打字",
        condition: "手机",
      },
      {
        label_path: ["功能", "触屏", "不灵敏"],
        sentiment: "NEGATIVE",
        source_ref: "REVIEWER",
        experiencer_ref: "REVIEWER",
        product_ref: "CURRENT",
        variant_ref: "SIZE_M",
        event_ref: "USE_1",
        reference_basis: "MARKET_NORM",
        part: "FINGER",
        operation: "打字",
        condition: "手机",
      },
    ];
    expect(
      semanticConclusions({ classification: { semantic_units: facts } })[0].status,
    ).toBe("CONFLICT");
    facts[1] = { ...facts[1], experiencer_ref: "OTHER_USER" };
    expect(
      semanticConclusions({ classification: { semantic_units: facts } })[0].status,
    ).toBe("MIXED");
  });

  test("未知语义按处置分流且正常弃权默认折叠", async () => {
    const user = userEvent.setup();
    const record = {
      classification: {
        unknown_semantics: [
          {
            fact_id: "U1",
            opinion: "缺少可映射标签",
            evidence: "missing label",
            reason: "当前标签体系未覆盖",
            disposition: "TAXONOMY_GAP",
          },
          {
            fact_id: "U2",
            opinion: "未来可能购买",
            evidence: "might buy another",
            reason: "意图不参与当前体验打标",
            disposition: "EXPECTED_ABSTENTION",
          },
          {
            fact_id: "U3",
            opinion: "旧结果未知语义",
            evidence: "legacy unknown",
          },
        ],
      },
    };

    expect(semanticUnknownGroups(record)).toMatchObject({
      review: [{ disposition: "TAXONOMY_GAP" }, { disposition: "" }],
      informational: [{ disposition: "EXPECTED_ABSTENTION" }],
    });
    render(<SemanticResultPanel record={record} />);

    expect(screen.getByRole("region", { name: "需要复核" })).toBeVisible();
    expect(screen.getByText("需要复核 · 2 项")).toBeVisible();
    expect(screen.getByText("标签体系缺口")).toBeVisible();
    expect(screen.getByText("旧结果未提供处置")).toBeVisible();
    expect(screen.getByText("未来可能购买")).not.toBeVisible();

    await user.click(screen.getByText("未参与打标信息 · 1 项"));
    expect(screen.getByText("未来可能购买")).toBeVisible();
    expect(screen.getByText("正常弃权")).toBeVisible();
    expect(screen.queryByText("未知语义")).not.toBeInTheDocument();
  });

  test("真实 API 顶层待复核与忽略事实会合并展示且不重复", async () => {
    const user = userEvent.setup();
    const duplicatedReviewItem = {
      fact_id: "U1",
      opinion: "当前标签体系没有对应的精细操作标签",
      evidence: "Fine typing is difficult.",
      reason: "标签体系未覆盖精细操作",
      disposition: "TAXONOMY_GAP",
    };
    const record = {
      unknown_semantics: [duplicatedReviewItem],
      ignored_semantics: [
        {
          fact_id: "I1",
          opinion: "以后可能会买更大尺码",
          evidence: "I might buy a larger size later.",
          reason: "未来购买意图不参与当前体验打标",
          disposition: "EXPECTED_ABSTENTION",
        },
        {
          fact_id: "I2",
          opinion: "尚未测试防水",
          evidence: "I have not tested them in rain.",
          reason: "未测试信息仅保留为上下文",
        },
      ],
      classification: {
        unknown_semantics: [duplicatedReviewItem],
      },
    };

    expect(semanticUnknownGroups(record)).toMatchObject({
      review: [{ factId: "U1" }],
      informational: [
        { factId: "I1", disposition: "EXPECTED_ABSTENTION" },
        { factId: "I2", disposition: "EXPECTED_ABSTENTION" },
      ],
    });
    render(<SemanticResultPanel record={record} />);

    expect(screen.getByText("需要复核 · 1 项")).toBeVisible();
    expect(screen.getByText("未参与打标信息 · 2 项")).toBeVisible();
    expect(screen.getAllByText("当前标签体系没有对应的精细操作标签")).toHaveLength(1);
    expect(screen.getByText("以后可能会买更大尺码")).not.toBeVisible();
    await user.click(screen.getByText("未参与打标信息 · 2 项"));
    expect(screen.getByText("以后可能会买更大尺码")).toBeVisible();
    expect(screen.getByText("尚未测试防水")).toBeVisible();
  });
});

test("看板以评论数展示互斥的评论级结论分布", () => {
  render(
    <ReturnReasonInsights
      route={{}}
      updateRoute={vi.fn()}
      loading={false}
      onEvidence={vi.fn()}
      data={{
        summary: {
          comment_count: 10,
          total_comment_count: 12,
          comment_statuses: {
            POSITIVE: 4,
            NEGATIVE: 2,
            MIXED: 2,
            CONFLICT: 1,
            NO_CONFIRMED: 1,
          },
        },
        date_range: {},
        filter_options: {},
        category_groups: [],
        reasons: [],
        hierarchy_problems: [],
        selected_reason: null,
        products: [],
        co_reasons: [],
        semantic_profile: {},
        evidence: { items: [], total: 0 },
      }}
    />,
  );

  const distribution = screen.getByRole("region", { name: "评论级结论分布" });
  expect(within(distribution).getByText("仅正向")).toBeVisible();
  expect(within(distribution).getByText("4")).toBeVisible();
  expect(within(distribution).getByText("疑似冲突")).toBeVisible();
  expect(
    screen.getByText(/同一反馈可命中多个原因，占比之和可能超过 100%/),
  ).toBeVisible();
});
