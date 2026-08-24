import { cleanup, render, screen, waitFor } from "@testing-library/react";
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
}));

vi.mock("../src/shared/api/classificationStandardApi", () => ({
  classificationStandardApi: standardApiMock,
}));

import { ClassificationStandardsPage } from "../src/features/classification-standards/ClassificationStandardsPage";

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

test("分类标准首页使用全宽列表并支持搜索", async () => {
  const { container } = render(
    <ClassificationStandardsPage route={{ query: {} }} notify={vi.fn()} />,
  );

  expect(await screen.findByRole("heading", { name: "分类标准" })).toBeVisible();
  expect(screen.getByRole("button", { name: "新建分类标准" })).toBeVisible();
  expect(screen.getByRole("columnheader", { name: "适用品类" })).toBeVisible();
  expect(screen.getByRole("button", { name: /眼镜分类标准/ })).toBeVisible();
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

test("查看页直接呈现品类、标签和运行版本说明", async () => {
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );

  expect(await screen.findByText("当前启用版本 V1")).toBeVisible();
  expect(screen.getByText("儿童眼镜")).toBeVisible();
  expect(screen.getByText("佩戴压迫")).toBeVisible();
  expect(screen.getByText("EYEWEAR_FIT_PRESSURE")).toBeVisible();
  expect(screen.getByText("关键词：pressure、tight")).toBeVisible();
  expect(screen.getByText(/历史任务始终保留原版本/)).toBeVisible();
  expect(screen.getByRole("link", { name: "导出 V1 JSON" })).toHaveAttribute(
    "href",
    `/api/classification-standard-versions/${standard.standard_version_id}/export`,
  );
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

  await userEvent.click(await screen.findByText("版本记录（2）"));
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
  expect(screen.getByDisplayValue("导入后的适用范围")).toBeVisible();
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
  expect(notify).toHaveBeenCalledWith("JSON 已导入草稿，请检查后再发布");
});

test("编辑页通过一次保存发布新版本且无需样本验证", async () => {
  const notify = vi.fn();
  standardApiMock.createClassificationStandardDraft.mockResolvedValue(draft);
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_draftId, payload) => ({
      ...validDraft,
      content: payload.content,
      change_reason: payload.change_reason,
    }),
  );
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

  const nameInput = await screen.findByDisplayValue("眼镜分类标准");
  await userEvent.clear(nameInput);
  await userEvent.type(nameInput, "眼镜退货分类标准");
  await userEvent.click(screen.getByRole("button", { name: "保存并启用" }));

  await waitFor(() =>
    expect(standardApiMock.publishClassificationStandardDraft).toHaveBeenCalledWith(
      draft.id,
      expect.objectContaining({ expected_revision: 2 }),
    ),
  );
  expect(standardApiMock.createClassificationStandardDraft).toHaveBeenCalledWith(
    standard.id,
  );
  expect(
    standardApiMock.createClassificationStandardValidationRun,
  ).not.toHaveBeenCalled();
  expect(notify).toHaveBeenCalledWith("分类标准已更新并启用");
});

test("新建页一次维护品类和标签并启用", async () => {
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
  standardApiMock.publishClassificationStandardDraft.mockResolvedValue({
    ...detail,
    id: createdDraft.standard_id,
    name: "背包分类标准",
  });

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
  await userEvent.type(screen.getByRole("textbox", { name: "品类 A 1" }), "箱包");
  await userEvent.type(screen.getByRole("textbox", { name: "品类 B 1" }), "户外背包");
  await userEvent.click(screen.getByRole("button", { name: "增加标签" }));
  await userEvent.type(screen.getByRole("textbox", { name: "标签分组 1" }), "商品质量");
  await userEvent.type(screen.getByRole("textbox", { name: "标签名称 1" }), "结构损坏");
  await userEvent.type(
    screen.getByRole("textbox", { name: "标签编码 1" }),
    "BACKPACK_DAMAGE",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "业务定义 1" }),
    "背包主体或拉链损坏",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "英文关键词 1" }),
    "damage, zipper",
  );
  await userEvent.click(screen.getByRole("button", { name: "保存并启用" }));

  await waitFor(() =>
    expect(standardApiMock.createClassificationStandard).toHaveBeenCalledWith({
      name: "背包分类标准",
      product_context: "户外背包",
      category_a: "箱包",
      category_b: "户外背包",
    }),
  );
  expect(standardApiMock.publishClassificationStandardDraft).toHaveBeenCalled();
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
  expect(notify).toHaveBeenCalledWith("分类标准已创建并启用");
});

test("删除已发布标准时明确执行停用", async () => {
  standardApiMock.deleteClassificationStandard.mockResolvedValue({
    id: standard.id,
    mode: "deactivated",
    status: "inactive",
  });

  render(<ClassificationStandardsPage route={{ query: {} }} notify={vi.fn()} />);

  await userEvent.click(await screen.findByRole("button", { name: "删除" }));
  expect(screen.getByText(`停用“${standard.name}”`)).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "确认停用" }));

  await waitFor(() =>
    expect(standardApiMock.deleteClassificationStandard).toHaveBeenCalledWith(
      standard.id,
    ),
  );
});
