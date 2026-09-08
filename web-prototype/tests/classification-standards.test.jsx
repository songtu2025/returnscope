import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

const standardApiMock = vi.hoisted(() => ({
  classificationStandards: vi.fn(),
  createClassificationStandard: vi.fn(),
  deleteClassificationStandard: vi.fn(),
  classificationStandard: vi.fn(),
  classificationStandardVersions: vi.fn(),
  classificationStandardDraft: vi.fn(),
  createClassificationStandardDraft: vi.fn(),
  updateClassificationStandardDraft: vi.fn(),
  importClassificationStandardDraft: vi.fn(),
  publishClassificationStandardDraft: vi.fn(),
  classificationStandardVersionExportUrl: vi.fn(),
  restoreClassificationStandardVersion: vi.fn(),
  classificationStandardValidationSources: vi.fn(),
  classificationStandardValidationRuns: vi.fn(),
  createClassificationStandardValidationRun: vi.fn(),
  classificationStandardValidationRun: vi.fn(),
  approveClassificationStandardValidationRun: vi.fn(),
}));

vi.mock("../src/shared/api/classificationStandardApi", () => ({
  classificationStandardApi: standardApiMock,
}));

import { ClassificationStandardsPage } from "../src/features/classification-standards/ClassificationStandardsPage";
import {
  reconcileLabelRules,
  sameLabel,
} from "../src/features/classification-standards/labelDraftPolicy";

const content = {
  name: "眼镜分类标准",
  product_context: "儿童及运动眼镜",
  instructions: ["识别眼镜佩戴和质量问题"],
  allowed_parts: ["UNSPECIFIED", "FRAME"],
  variants: [{ category_a: "眼镜", category_b: "儿童眼镜", attributes: {} }],
  labels: [
    {
      code: "EYEWEAR_FIT_PRESSURE",
      name: "佩戴压迫",
      group: "尺码与适配",
      description: "镜框或镜腿造成压迫",
      keywords: ["pressure", "tight"],
      allowed_sentiments: ["NEGATIVE"],
    },
  ],
};

const snapshot = {
  standard_key: "eyewear",
  name: content.name,
  agent_family: "眼镜退货语义智能体",
  logic_version: "eyewear-semantic-v1",
  model_policy: { version: "eyewear-policy-v1" },
  variants: content.variants,
  taxonomy: {
    version: "eyewear-taxonomy-v1",
    agent_family: "眼镜退货语义智能体",
    product_context: content.product_context,
    instructions: content.instructions,
    allowed_parts: content.allowed_parts,
    labels: content.labels,
  },
};

const standard = {
  id: "classification-standard-eyewear",
  standard_key: "eyewear",
  name: content.name,
  status: "active",
  version_no: 1,
  standard_version_id: "classification-standard-version-eyewear-v1",
  product_context: content.product_context,
  agent_family: "眼镜退货语义智能体",
  category_count: 1,
  label_count: 1,
  label_group_count: 1,
  task_segment_count: 3,
  result_count: 2,
  published_version_count: 1,
  delete_mode: "deactivate",
  updated_at: "2026-08-19T00:00:00Z",
};

const detail = { ...standard, snapshot, draft_id: null };

const draft = {
  id: "classification-standard-draft-eyewear",
  standard_id: standard.id,
  standard_key: standard.standard_key,
  standard_name: standard.name,
  is_new: false,
  base_version_id: standard.standard_version_id,
  base_version_no: 1,
  revision: 1,
  change_reason: "",
  content,
  base_snapshot: snapshot,
  validation: {
    blocking: ["草稿与当前已发布版本没有差异"],
    warnings: [],
  },
  diff: { has_changes: false },
  impact: { task_segment_count: 3, result_count: 2 },
};

const validDraft = {
  ...draft,
  revision: 2,
  validation: { blocking: [], warnings: [] },
  diff: { has_changes: true },
};

const readyRun = {
  id: "classification-standard-validation-ready",
  draft_id: draft.id,
  draft_revision: validDraft.revision,
  status: "completed",
  sample_size: 20,
  processed_count: 20,
  error_count: 0,
  is_current: true,
  publication_ready: true,
  approved_by_name: "测试用户",
  approved_at: "2026-08-25T08:00:00Z",
  approval_note: "差异符合预期",
  source: { listing: "Listing-1" },
  summary: {
    sample_size: 20,
    changed_count: 0,
    changed_rate: 0,
    coverage_count: 20,
    coverage_rate: 100,
    review_count: 0,
    review_rate: 0,
    unknown_count: 0,
    unknown_rate: 0,
    error_count: 0,
    error_rate: 0,
  },
  model_names: ["test-model"],
  items: [],
};

const awaitingApprovalRun = {
  ...readyRun,
  id: "classification-standard-validation-awaiting-approval",
  publication_ready: false,
  approved_by_name: null,
  approved_at: null,
  approval_note: "",
  source: {
    kind: "raw_dataset",
    comparison_mode: "baseline_and_draft",
    listing: "Listing-1",
  },
};

beforeEach(() => {
  Object.values(standardApiMock).forEach((mock) => mock.mockReset());
  standardApiMock.classificationStandards.mockResolvedValue([standard]);
  standardApiMock.classificationStandard.mockResolvedValue(detail);
  standardApiMock.classificationStandardVersions.mockResolvedValue([
    {
      id: standard.standard_version_id,
      version_no: 1,
      version_reason: "初始化",
      published_at: "2026-08-19T00:00:00Z",
    },
  ]);
  standardApiMock.classificationStandardVersionExportUrl.mockImplementation(
    (versionId) => `/api/classification-standard-versions/${versionId}/export`,
  );
  standardApiMock.classificationStandardValidationSources.mockResolvedValue([]);
  standardApiMock.classificationStandardValidationRuns.mockResolvedValue([]);
  window.location.hash = "";
});

afterEach(() => cleanup());

test("停用和恢复标签同步校验引用，且不修改原配置", () => {
  const rules = {
    opposite_reason_labels: { SMALL: ["A", "B"] },
    conflicting_label_sets: [
      ["A", "B"],
      ["B", "C"],
    ],
    evidence_requirements: [
      {
        label_code: "A",
        cues: ["hole"],
        unknown_opinion: "未知",
        unknown_reason: "证据不足",
      },
    ],
    implicit_evidence_rules: [{ label_code: "A", cues: ["bigger"] }],
    claim_evidence_requirements: [
      { label_code: "A", claim_id: "CLAIM", cues: ["dry"] },
    ],
  };
  const before = structuredClone(rules);
  const filtered = reconcileLabelRules(rules, [{ code: "B" }, { code: "C" }]);
  expect(filtered.conflicting_label_sets).toEqual([["B", "C"]]);
  expect(filtered.opposite_reason_labels.SMALL).toEqual(["B"]);
  expect(filtered.evidence_requirements).toEqual([]);
  const restored = reconcileLabelRules(
    filtered,
    [{ code: "A" }, { code: "B" }, { code: "C" }],
    rules,
    "A",
  );
  expect(restored.conflicting_label_sets).toContainEqual(["A", "B"]);
  expect(restored.evidence_requirements).toEqual(rules.evidence_requirements);
  expect(restored.implicit_evidence_rules).toEqual(rules.implicit_evidence_rules);
  expect(restored.claim_evidence_requirements).toEqual(
    rules.claim_evidence_requirements,
  );
  expect(rules).toEqual(before);
  expect(
    sameLabel(content.labels[0], { ...content.labels[0], allowed_claim_ids: [] }),
  ).toBe(true);
});

test("工作台切换标签保留批量关键词，保存草稿不触发发布", async () => {
  const another = {
    ...content.labels[0],
    code: "QUALITY_DURABLE",
    name: "耐用",
    group: "质量",
    keywords: [],
  };
  const source = { ...content, labels: [...content.labels, another] };
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    snapshot: {
      ...snapshot,
      taxonomy: { ...snapshot.taxonomy, labels: source.labels },
    },
  });
  standardApiMock.createClassificationStandardDraft.mockResolvedValue({
    ...draft,
    content: source,
  });
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_id, payload) => ({ ...validDraft, content: payload.content }),
  );
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(await screen.findByText(/搜索别名（可选）/));
  const input = await screen.findByRole("textbox", { name: "搜索别名 1" });
  await userEvent.type(input, "soft; comfy, soft{Enter}");
  await userEvent.click(screen.getByRole("button", { name: /耐用/ }));
  expect(screen.queryByRole("dialog")).toBeNull();
  if (!screen.getByText(/搜索别名（可选）/).closest("details").open)
    await userEvent.click(screen.getByText(/搜索别名（可选）/));
  expect(screen.getByRole("textbox", { name: "搜索别名 2" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: /佩戴压迫.*已修改/ }));
  if (!screen.getByText(/搜索别名（可选）/).closest("details").open)
    await userEvent.click(screen.getByText(/搜索别名（可选）/));
  expect(screen.getByRole("button", { name: "移除搜索别名 comfy" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() =>
    expect(standardApiMock.updateClassificationStandardDraft).toHaveBeenCalled(),
  );
  const payload = standardApiMock.updateClassificationStandardDraft.mock.calls[0][1];
  expect(payload.content.labels[0].keywords).toEqual([
    "pressure",
    "tight",
    "soft",
    "comfy",
  ]);
  expect(payload.content.labels[1]).toEqual(another);
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("替代标签生成新编码并清理旧引用，检查变更后才可保存", async () => {
  const another = { ...content.labels[0], code: "FIT_LOOSE", name: "偏松" };
  const rules = { conflicting_label_sets: [[content.labels[0].code, another.code]] };
  const source = {
    ...content,
    validation_rules: rules,
    labels: [...content.labels, another],
  };
  const sourceSnapshot = {
    ...snapshot,
    taxonomy: { ...snapshot.taxonomy, labels: source.labels, validation_rules: rules },
  };
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    snapshot: sourceSnapshot,
  });
  standardApiMock.createClassificationStandardDraft.mockResolvedValue({
    ...draft,
    content: source,
    base_snapshot: sourceSnapshot,
  });
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_id, payload) => ({
      ...validDraft,
      content: payload.content,
      base_snapshot: sourceSnapshot,
    }),
  );
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: /修改定义：创建替代标签/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "创建替代标签", exact: true }),
  );
  expect(screen.getByRole("textbox", { name: "标签编码 1" })).toHaveValue(
    "EYEWEAR_FIT_PRESSURE_V2",
  );
  await userEvent.clear(screen.getByRole("textbox", { name: "业务定义 1" }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "业务定义 1" }),
    "明确描述鼻托压迫",
  );
  await userEvent.click(screen.getByRole("button", { name: "发布", exact: true }));
  const preview = screen
    .getByRole("heading", { name: "发布前检查" })
    .closest("section");
  expect(within(preview).getByText("新增")).toBeVisible();
  expect(within(preview).getByText("拟停用")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() =>
    expect(standardApiMock.updateClassificationStandardDraft).toHaveBeenCalled(),
  );
  const payload = standardApiMock.updateClassificationStandardDraft.mock.calls[0][1];
  expect(payload.content.labels.map((item) => item.code)).toEqual([
    "EYEWEAR_FIT_PRESSURE_V2",
    "FIT_LOOSE",
  ]);
  expect(payload.content.validation_rules.conflicting_label_sets).toEqual([]);
  expect(sourceSnapshot.taxonomy.validation_rules).toEqual(rules);
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("标签搜索覆盖定义关键词编码，切换分组保留搜索并支持重置", async () => {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    snapshot: {
      ...snapshot,
      taxonomy: {
        ...snapshot.taxonomy,
        labels: [
          ...content.labels,
          {
            code: "QUALITY_CRACK",
            name: "镜框断裂",
            group: "质量",
            description: "镜框出现裂纹",
            keywords: ["crack", "broken"],
            allowed_sentiments: ["NEGATIVE"],
          },
        ],
      },
    },
  });
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  const search = await screen.findByRole("searchbox", { name: "搜索标签" });
  await userEvent.type(search, "TIGHT");
  expect(screen.getByRole("button", { name: /佩戴压迫.*尺码与适配/ })).toBeVisible();
  expect(screen.queryByRole("button", { name: /镜框断裂.*质量/ })).toBeNull();
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "筛选标签分组" }),
    "质量",
  );
  expect(search).toHaveValue("TIGHT");
  expect(screen.getByText("没有匹配的标签。")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "重置筛选" }));
  for (const term of ["QUALITY_CRACK", "裂纹", "断裂"]) {
    await userEvent.clear(search);
    await userEvent.type(search, term);
    expect(screen.getByRole("button", { name: /镜框断裂.*质量/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /佩戴压迫.*尺码与适配/ })).toBeNull();
  }
  expect(standardApiMock.updateClassificationStandardDraft).not.toHaveBeenCalled();
});

test("查看与编辑原位切换，保留搜索、选中标签和未保存内容", async () => {
  const user = userEvent.setup();
  const copy = vi.spyOn(navigator.clipboard, "writeText");
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  const search = await screen.findByRole("searchbox", { name: "搜索标签" });
  await user.type(search, "pressure");
  expect(screen.queryByRole("textbox", { name: "搜索别名 1" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "复制标签编码" }));
  expect(copy).toHaveBeenCalledWith("EYEWEAR_FIT_PRESSURE");
  await user.click(screen.getByRole("button", { name: "编辑", exact: true }));
  await user.click(screen.getByText(/搜索别名（可选）/));
  await user.type(screen.getByRole("textbox", { name: "搜索别名 1" }), "soft{Enter}");
  await user.click(screen.getByRole("button", { name: "完成编辑" }));
  expect(search).toHaveValue("pressure");
  expect(screen.getByText("soft")).toBeVisible();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(window.location.hash).toBe("");
  await user.click(screen.getByRole("button", { name: "返回" }));
  expect(screen.getByRole("dialog", { name: "离开编辑页？" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "继续编辑" }));
  expect(screen.getByText("soft")).toBeVisible();
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
  copy.mockRestore();
});

test("分类标准首页使用全宽列表并支持搜索", async () => {
  const { container } = render(
    <ClassificationStandardsPage route={{ query: {} }} notify={vi.fn()} />,
  );

  expect(await screen.findByRole("heading", { name: "分类标准" })).toBeVisible();
  expect(screen.getByRole("button", { name: "新建分类标准" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "适用品类" })).toBeVisible();
  expect(
    screen.getByRole("button", { name: /^眼镜分类标准/ }),
  ).toBeVisible();
  expect(container.querySelector(".classification-standard-layout")).toBeNull();
  expect(screen.getByRole("group", { name: "标准状态" })).toBeVisible();
  expect(screen.getByRole("button", { name: "全部状态" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );

  await userEvent.click(screen.getByRole("button", { name: "未使用" }));
  expect(await screen.findByText("没有符合条件的分类标准")).toBeVisible();

  await userEvent.click(screen.getByRole("button", { name: "全部状态" }));

  await userEvent.type(screen.getByRole("textbox", { name: "搜索分类标准" }), "不存在");
  expect(await screen.findByText("没有符合条件的分类标准")).toBeVisible();
});

test("工作台收纳设置和版本记录，不显示重复未修改状态", async () => {
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  expect(await screen.findByText("当前启用版本 V1")).toBeVisible();
  expect(screen.getByText("EYEWEAR_FIT_PRESSURE")).toBeVisible();
  await userEvent.click(screen.getByText(/搜索别名（可选）/));
  expect(screen.getByText("pressure")).toBeVisible();
  expect(screen.queryByText("未修改")).toBeNull();
  expect(screen.queryByRole("button", { name: "管理标准" })).toBeNull();
  expect(screen.queryByRole("button", { name: "检查变更", exact: true })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "标准设置" }));
  expect(screen.getByRole("textbox", { name: "品类 B 1" })).toHaveValue("儿童眼镜");
  await userEvent.click(screen.getByText("版本记录（1）"));
  expect(screen.getByRole("link", { name: "导出 V1 JSON" })).toHaveAttribute(
    "href",
    `/api/classification-standard-versions/${standard.standard_version_id}/export`,
  );
});

test("工作台明确展示未发布草稿，可原位继续编辑", async () => {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: draft.id,
    draft_revision: draft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue({
    ...draft,
    content: {
      ...content,
      labels: [{ ...content.labels[0], keywords: ["draft keyword"] }],
    },
  });
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  expect(await screen.findByText("未发布草稿 r1 · 当前启用版本 V1")).toBeVisible();
  await userEvent.click(screen.getByText(/搜索别名（可选）/));
  expect(screen.getByText("draft keyword")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "编辑", exact: true }));
  expect(screen.getByRole("textbox", { name: "搜索别名 1" })).toBeEnabled();
  expect(standardApiMock.createClassificationStandardDraft).not.toHaveBeenCalled();
});

test("历史版本只能恢复为新草稿", async () => {
  const notify = vi.fn();
  const versionV2Id = "classification-standard-version-eyewear-v2";
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    version_no: 2,
    standard_version_id: versionV2Id,
  });
  standardApiMock.classificationStandardVersions.mockResolvedValue([
    {
      id: versionV2Id,
      version_no: 2,
      version_reason: "发布 V2",
      published_at: "2026-08-20T00:00:00Z",
    },
    {
      id: standard.standard_version_id,
      version_no: 1,
      version_reason: "初始化",
      published_at: "2026-08-19T00:00:00Z",
    },
  ]);
  standardApiMock.restoreClassificationStandardVersion.mockResolvedValue(draft);

  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={notify}
    />,
  );

  await userEvent.click(await screen.findByRole("button", { name: "标准设置" }));
  await userEvent.click(screen.getByText("版本记录（2）"));
  expect(screen.queryByRole("button", { name: "恢复 V2 为草稿" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "恢复 V1 为草稿" }));
  expect(screen.getByRole("dialog", { name: "恢复 V1 为新草稿" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "创建恢复草稿" }));

  await waitFor(() =>
    expect(standardApiMock.restoreClassificationStandardVersion).toHaveBeenCalledWith(
      standard.standard_version_id,
    ),
  );
  expect(notify).toHaveBeenCalledWith("已从 V1 创建恢复草稿，请检查后再发布");
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("编辑页将JSON导入草稿但不直接发布", async () => {
  const notify = vi.fn();
  const importedContent = { ...content, product_context: "导入后的适用范围" };
  standardApiMock.createClassificationStandardDraft.mockResolvedValue(draft);
  standardApiMock.importClassificationStandardDraft.mockResolvedValue({
    ...validDraft,
    content: importedContent,
    change_reason: "导入 eyewear.json",
  });

  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={notify}
    />,
  );

  const file = new File(["{}"], "eyewear.json", { type: "application/json" });
  file.text = vi
    .fn()
    .mockResolvedValue(
      JSON.stringify({ format: "classification-standard", format_version: 1 }),
    );
  await userEvent.click(
    await screen.findByRole("button", { name: "标准设置", exact: true }),
  );
  await userEvent.upload(await screen.findByLabelText("选择分类标准 JSON 文件"), file);

  await waitFor(() =>
    expect(standardApiMock.importClassificationStandardDraft).toHaveBeenCalledWith(
      draft.id,
      expect.objectContaining({
        expected_revision: draft.revision,
        change_reason: "导入 eyewear.json",
      }),
    ),
  );
  await userEvent.click(screen.getByRole("button", { name: "标准设置", exact: true }));
  expect(screen.getByDisplayValue("导入后的适用范围")).toBeVisible();
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
  expect(notify).toHaveBeenCalledWith("JSON 已导入草稿，请检查后再发布");
});

test("高级设置的部位由当前标准驱动并可新增", async () => {
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "标准设置", exact: true }),
  );

  await userEvent.click(screen.getByText("高级分类设置"));
  expect(screen.getByText("未指定部位")).toBeVisible();
  expect(screen.getAllByText("FRAME").length).toBeGreaterThan(0);
  expect(screen.queryByText("手背")).not.toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("新增证据部位编码"), "knuckle_guard");
  await userEvent.click(screen.getByRole("button", { name: "新增部位" }));

  expect(screen.getAllByText("KNUCKLE_GUARD").length).toBeGreaterThan(0);
});

test("已发布标签的编码和语义不可直接修改", async () => {
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );

  expect(await screen.findByRole("complementary", { name: "标签目录" })).toBeVisible();
  for (const name of ["标签分组 1", "标签名称 1", "标签编码 1", "业务定义 1"])
    expect(screen.queryByRole("textbox", { name })).toBeNull();
  expect(screen.getByText("镜框或镜腿造成压迫")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "搜索别名 1" })).toBeEnabled();
  expect(screen.getByRole("button", { name: /修改定义：创建替代标签/ })).toBeVisible();
});

test("编辑页只允许发布当前修订已验证的草稿", async () => {
  const notify = vi.fn();
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
    draft_revision: validDraft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(validDraft);
  standardApiMock.classificationStandardValidationRuns.mockResolvedValue([readyRun]);
  standardApiMock.classificationStandardValidationRun.mockResolvedValue(readyRun);
  standardApiMock.publishClassificationStandardDraft.mockResolvedValue({
    ...detail,
    version_no: 2,
  });

  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={notify}
    />,
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "发布", exact: true }),
  );
  await userEvent.click(await screen.findByRole("button", { name: "发布并启用" }));

  await waitFor(() =>
    expect(standardApiMock.publishClassificationStandardDraft).toHaveBeenCalledWith(
      draft.id,
      expect.objectContaining({ expected_revision: 2 }),
    ),
  );
  expect(notify).toHaveBeenCalledWith("分类标准已更新并启用");
});

test("草稿未完成样本验证时禁止发布", async () => {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
    draft_revision: validDraft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(validDraft);

  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "发布", exact: true }),
  );
  expect(await screen.findByRole("button", { name: "等待样本验证" })).toBeDisabled();
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("原始数据验证完成后必须人工确认才能发布", async () => {
  const notify = vi.fn();
  const rawSource = {
    result_version_id: "raw:returns-v1:products-v1",
    source_kind: "raw_dataset",
    return_dataset_name: "真实手套退货评论",
    product_dataset_name: "商品信息汇总",
    version_no: 1,
  };
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
    draft_revision: validDraft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(validDraft);
  standardApiMock.classificationStandardValidationSources.mockResolvedValue([
    rawSource,
  ]);
  standardApiMock.classificationStandardValidationRuns.mockResolvedValue([
    awaitingApprovalRun,
  ]);
  standardApiMock.classificationStandardValidationRun.mockResolvedValue(
    awaitingApprovalRun,
  );
  standardApiMock.approveClassificationStandardValidationRun.mockResolvedValue({
    ...awaitingApprovalRun,
    publication_ready: true,
    approved_at: "2026-08-25T08:00:00Z",
  });

  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={notify}
    />,
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "发布", exact: true }),
  );
  expect(
    await screen.findByRole("option", { name: /真实手套退货评论/ }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "等待人工确认" })).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /我已审阅/ }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "验证结论" }),
    "差异符合预期",
  );
  await userEvent.click(screen.getByRole("button", { name: "确认验证通过" }));

  await waitFor(() =>
    expect(
      standardApiMock.approveClassificationStandardValidationRun,
    ).toHaveBeenCalledWith(awaitingApprovalRun.id, {
      expected_revision: validDraft.revision,
      note: "差异符合预期",
    }),
  );
  expect(notify).toHaveBeenCalledWith("当前草稿修订已人工确认，可进入发布确认");
});

test("新建页一次维护品类和标签并保存草稿", async () => {
  const notify = vi.fn();
  const createdDraft = {
    ...draft,
    id: "classification-standard-draft-backpack",
    standard_id: "classification-standard-backpack",
    is_new: true,
    base_version_no: 0,
    content: {
      ...content,
      name: "背包分类标准",
      product_context: "户外背包",
      variants: [{ category_a: "箱包", category_b: "户外背包", attributes: {} }],
      labels: [],
    },
  };
  standardApiMock.createClassificationStandard.mockResolvedValue(createdDraft);
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_draftId, payload) => ({
      ...createdDraft,
      revision: 2,
      content: payload.content,
      validation: { blocking: [], warnings: [] },
    }),
  );
  render(
    <ClassificationStandardsPage route={{ query: { view: "new" } }} notify={notify} />,
  );

  await userEvent.type(
    await screen.findByRole("textbox", { name: "标准名称" }),
    "背包分类标准",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "适用商品说明" }),
    "户外背包",
  );
  await userEvent.click(screen.getByRole("button", { name: "标准设置", exact: true }));
  await userEvent.type(screen.getByRole("textbox", { name: "品类 A 1" }), "箱包");
  await userEvent.type(screen.getByRole("textbox", { name: "品类 B 1" }), "户外背包");
  await userEvent.click(screen.getByRole("button", { name: "标签管理", exact: true }));
  await userEvent.click(screen.getByRole("button", { name: "增加标签", exact: true }));
  await userEvent.selectOptions(screen.getByLabelText("标签分组 1"), "质量与耐用");
  await userEvent.type(screen.getByRole("textbox", { name: "标签名称 1" }), "结构损坏");
  await userEvent.clear(screen.getByRole("textbox", { name: "标签编码 1" }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "标签编码 1" }),
    "BACKPACK_DAMAGE",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "业务定义 1" }),
    "背包主体或拉链损坏",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "搜索别名 1" }),
    "damage, zipper",
  );
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));

  await waitFor(() =>
    expect(standardApiMock.createClassificationStandard).toHaveBeenCalledWith({
      name: "背包分类标准",
      product_context: "户外背包",
      category_a: "箱包",
      category_b: "户外背包",
    }),
  );
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
  expect(standardApiMock.updateClassificationStandardDraft).toHaveBeenCalledWith(
    createdDraft.id,
    expect.objectContaining({
      content: expect.objectContaining({
        labels: expect.arrayContaining([
          expect.objectContaining({ keywords: ["damage", "zipper"] }),
        ]),
      }),
    }),
  );
  expect(notify).toHaveBeenCalledWith("修改已保存");
});

test("删除已发布标准时明确执行停用", async () => {
  standardApiMock.classificationStandards.mockResolvedValue([
    { ...standard, draft_id: draft.id },
  ]);
  standardApiMock.deleteClassificationStandard.mockResolvedValue({
    id: standard.id,
    mode: "deactivated",
    status: "inactive",
  });

  render(<ClassificationStandardsPage route={{ query: {} }} notify={vi.fn()} />);

  const deactivate = await screen.findByRole("button", { name: `停用标准：${standard.name}` });
  expect(screen.queryByText("更多")).not.toBeInTheDocument();
  await userEvent.click(deactivate);
  expect(screen.getByText(`停用“${standard.name}”`)).toBeVisible();
  expect(screen.getByText("停用分类标准")).toBeVisible();
  expect(screen.getByText(/草稿及其样本验证记录将一并删除，无法恢复/)).toBeVisible();
  expect(standardApiMock.deleteClassificationStandard).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(deactivate).toHaveFocus();
  await userEvent.click(deactivate);
  await userEvent.click(screen.getByRole("button", { name: "确认停用" }));

  await waitFor(() =>
    expect(standardApiMock.deleteClassificationStandard).toHaveBeenCalledWith(
      standard.id,
    ),
  );
});

test("已停用标准不再显示停用入口，未发布标准使用删除文案", async () => {
  standardApiMock.classificationStandards.mockResolvedValue([
    { ...standard, status: "inactive" },
    { ...standard, id: "unpublished", name: "未发布标准", status: "inactive", version_no: 0, delete_mode: "delete" },
  ]);
  render(<ClassificationStandardsPage route={{ query: {} }} notify={vi.fn()} />);
  await screen.findByText("已停用");
  expect(screen.queryByRole("button", { name: /^停用标准/ })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "删除标准：未发布标准" }));
  expect(screen.getByText("永久删除“未发布标准”")).toBeVisible();
  expect(screen.getByRole("button", { name: "确认删除" })).toBeVisible();
  expect(screen.queryByText(/草稿及其样本验证记录/)).not.toBeInTheDocument();
});

test("停用标准保持可浏览，设置禁止修改", async () => {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    status: "inactive",
  });
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  expect(await screen.findByRole("searchbox", { name: "搜索标签" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "编辑", exact: true })).toBeNull();
  expect(screen.queryByRole("button", { name: "增加标签" })).toBeNull();
  expect(screen.queryByText("更多")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "标准设置" }));
  expect(screen.getByRole("textbox", { name: "标准名称" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "增加品类" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "保存草稿" })).toBeNull();
});

test("Review 上传入口不依赖退货数据资产", async () => {
  const { ClassificationStandardValidation } =
    await import("../src/features/classification-standards/ClassificationStandardValidation");
  const onRun = vi.fn();
  render(
    <ClassificationStandardValidation
      draft={{ validation: { blocking: [] } }}
      sources={[]}
      runs={[]}
      sourceId=""
      sampleSize={20}
      busy={false}
      approvalBusy={false}
      onRun={onRun}
      onSourceChange={vi.fn()}
      onSampleSizeChange={vi.fn()}
    />,
  );
  const button = screen.getByRole("button", { name: "开始样本验证" });
  expect(button).toBeDisabled();
  const file = new File(["test"], "reviews.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  await userEvent.upload(screen.getByLabelText("Review 表格"), file);
  expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(onRun).toHaveBeenCalledWith(file, "standard_version");
});

test("停用与恢复标签同步维护中性原因和强制复核规则", () => {
  const rules = {
    neutral_reason_labels: ["BUYER"],
    required_review_labels: ["UNKNOWN"],
  };
  const removed = reconcileLabelRules(rules, [{ code: "UNKNOWN" }]);
  expect(removed.neutral_reason_labels).toEqual([]);
  const restored = reconcileLabelRules(
    removed,
    [{ code: "UNKNOWN" }, { code: "BUYER" }],
    rules,
    "BUYER",
  );
  expect(restored.neutral_reason_labels).toEqual(["BUYER"]);
  expect(restored.required_review_labels).toEqual(["UNKNOWN"]);
});

test("语义策略保存边界示例并将别名降为搜索用途", async () => {
  const semanticContent = { ...content, recognition_profile: "semantic_v1" };
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: draft.id,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue({
    ...validDraft,
    content: semanticContent,
  });
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_id, payload) => ({
      ...validDraft,
      content: payload.content,
    }),
  );
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "编辑", exact: true }),
  );
  await userEvent.type(
    screen.getByLabelText("排除说明"),
    "不能从未来担忧推断已经损坏。",
  );
  await userEvent.click(screen.getByRole("button", { name: "增加示例" }));
  await userEvent.type(screen.getByLabelText("示例原文 1"), "I worry it might break.");
  await userEvent.selectOptions(screen.getByLabelText("示例判定 1"), "false");
  expect(screen.queryByLabelText("示例评价方向 1")).toBeNull();
  await userEvent.type(screen.getByLabelText("示例说明 1"), "尚未实际发生。");
  await userEvent.click(screen.getByText(/搜索别名（可选）/));
  expect(
    screen.getByText("仅用于管理页面搜索，不参与当前语义策略分类。"),
  ).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() =>
    expect(standardApiMock.updateClassificationStandardDraft).toHaveBeenCalled(),
  );
  const saved =
    standardApiMock.updateClassificationStandardDraft.mock.calls[0][1].content;
  expect(saved.recognition_profile).toBe("semantic_v1");
  expect(saved.labels[0].exclusions).toEqual(["不能从未来担忧推断已经损坏。"]);
  expect(saved.labels[0].examples[0]).toMatchObject({
    applies: false,
    sentiment: null,
  });
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});
