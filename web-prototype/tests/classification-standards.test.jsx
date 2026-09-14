import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  act,
  cleanup,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
  validateClassificationStandardDraft: vi.fn(),
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

const validationApiMock = {
  sources: standardApiMock.classificationStandardValidationSources,
  runs: standardApiMock.classificationStandardValidationRuns,
  run: standardApiMock.classificationStandardValidationRun,
  start: standardApiMock.createClassificationStandardValidationRun,
};

vi.mock("../src/shared/api/classificationStandardApi", () => ({
  classificationStandardApi: standardApiMock,
}));

import { ClassificationStructureIssues } from "../src/features/classification-standards/ClassificationStructureIssues";
import { ClassificationStandardsPage } from "../src/features/classification-standards/ClassificationStandardsPage";
import { useClassificationStandardDraftController } from "../src/features/classification-standards/useClassificationStandardDraftController";
import { useClassificationStandardValidationController } from "../src/features/classification-standards/useClassificationStandardValidationController";
import {
  reconcileLabelRules,
  sameLabel,
} from "../src/features/classification-standards/labelDraftPolicy";
import { formatDate } from "../src/lib/presentation";

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
  standardApiMock.validateClassificationStandardDraft.mockImplementation(
    async () =>
      await (standardApiMock.updateClassificationStandardDraft.mock.results.at(-1)
        ?.value ??
        standardApiMock.classificationStandardDraft.mock.results.at(-1)?.value ??
        validDraft),
  );
  window.location.hash = "";
});

afterEach(() => {
  vi.restoreAllMocks();
  cleanup();
});

const validationSource = {
  result_version_id: "raw:returns-v1:products-v1",
  source_kind: "raw_dataset",
  return_dataset_name: "真实手套退货评论",
  product_dataset_name: "商品信息汇总",
  version_no: 1,
};

function mockEditableDraft({ sources = [], runs = [] } = {}) {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
    draft_revision: validDraft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(validDraft);
  validationApiMock.sources.mockResolvedValue(sources);
  validationApiMock.runs.mockResolvedValue(runs);
  if (runs[0]) validationApiMock.run.mockResolvedValue(runs[0]);
}

function renderEditPage(notify = vi.fn()) {
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={notify}
    />,
  );
  return notify;
}

function deferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function renderDraftController(initialProps) {
  const notify = vi.fn();
  return renderHook(
    (props) =>
      useClassificationStandardDraftController({
        ...props,
        notify,
        loadStandards: vi.fn(),
        setBusy: vi.fn(),
      }),
    { initialProps },
  );
}

function renderValidationController() {
  const notify = vi.fn();
  const setBusy = vi.fn();
  return {
    ...renderHook(() =>
      useClassificationStandardValidationController({
        draft: validDraft,
        notify,
        persistDraft: vi.fn().mockResolvedValue(validDraft),
        setBusy,
      }),
    ),
    notify,
    setBusy,
  };
}

async function openPublishReview() {
  await userEvent.click(
    await screen.findByRole("button", { name: "发布", exact: true }),
  );
}

test("详情加载仅提交最新标准，并在切换新建或列表页时失效", async () => {
  const staleDetail = deferred();
  const nextStandard = {
    ...detail,
    id: "classification-standard-gloves",
    name: "手套分类标准",
  };
  standardApiMock.classificationStandard.mockImplementation((standardId) =>
    standardId === standard.id ? staleDetail.promise : Promise.resolve(nextStandard),
  );
  standardApiMock.classificationStandardVersions.mockResolvedValue([]);
  const { result, rerender, unmount } = renderDraftController({
    mode: "edit",
    selectedId: standard.id,
  });

  rerender({ mode: "edit", selectedId: nextStandard.id });
  await waitFor(() => expect(result.current.detail?.id).toBe(nextStandard.id));
  await act(async () => {
    staleDetail.resolve(detail);
    await staleDetail.promise;
  });

  expect(result.current.detail?.id).toBe(nextStandard.id);
  expect(result.current.pageLoading).toBe(false);

  for (const mode of ["new", "list"]) {
    const staleRouteDetail = deferred();
    standardApiMock.classificationStandard.mockReturnValueOnce(
      staleRouteDetail.promise,
    );
    rerender({ mode: "edit", selectedId: `${standard.id}-${mode}` });
    rerender({ mode, selectedId: "" });
    await act(async () => {
      staleRouteDetail.resolve({ ...detail, draft_id: validDraft.id });
      await staleRouteDetail.promise;
    });
    expect(result.current.detail).toBeNull();
  }
  expect(validationApiMock.sources).not.toHaveBeenCalled();

  const unmountedDetail = deferred();
  standardApiMock.classificationStandard.mockReturnValueOnce(unmountedDetail.promise);
  rerender({ mode: "edit", selectedId: `${standard.id}-unmounted` });
  unmount();
  await act(async () => {
    unmountedDetail.resolve({ ...detail, draft_id: validDraft.id });
    await unmountedDetail.promise;
  });
  expect(validationApiMock.sources).not.toHaveBeenCalled();
  expect(validationApiMock.runs).not.toHaveBeenCalled();
});

test("验证状态仅提交最新加载且清空会使在途请求失效", async () => {
  const staleRunDetail = deferred();
  const oldRun = { ...readyRun, id: "validation-old" };
  const nextRun = { ...readyRun, id: "validation-next" };
  validationApiMock.sources.mockImplementation((draftId) =>
    Promise.resolve([{ ...validationSource, result_version_id: `${draftId}:source` }]),
  );
  validationApiMock.runs.mockImplementation((draftId) =>
    Promise.resolve([draftId === "draft-old" ? oldRun : nextRun]),
  );
  validationApiMock.run.mockImplementation((runId) =>
    runId === oldRun.id ? staleRunDetail.promise : Promise.resolve(nextRun),
  );
  const { result } = renderValidationController();

  let staleLoad;
  await act(async () => {
    staleLoad = result.current.loadValidation("draft-old");
    await waitFor(() => expect(validationApiMock.run).toHaveBeenCalledWith(oldRun.id));
  });
  await act(async () => result.current.loadValidation("draft-next"));
  await act(async () => {
    staleRunDetail.resolve(oldRun);
    await staleLoad;
  });
  expect(result.current.selectedValidation?.id).toBe(nextRun.id);
  expect(result.current.validationSources[0]?.result_version_id).toBe(
    "draft-next:source",
  );

  const pendingSources = deferred();
  const pendingRuns = deferred();
  validationApiMock.sources.mockReturnValueOnce(pendingSources.promise);
  validationApiMock.runs.mockReturnValueOnce(pendingRuns.promise);
  let pendingLoad;
  act(() => {
    pendingLoad = result.current.loadValidation("draft-pending");
    result.current.clearValidation();
  });
  await act(async () => {
    pendingSources.resolve([validationSource]);
    pendingRuns.resolve([oldRun]);
    await pendingLoad;
  });
  expect(result.current.validationSources).toEqual([]);
  expect(result.current.validationRuns).toEqual([]);
  expect(result.current.selectedValidation).toBeNull();
});

test("前台指定运行后轮询继续刷新该运行而不回选旧记录", async () => {
  const oldRun = { ...readyRun, id: "validation-old", status: "running" };
  const nextRun = { ...readyRun, id: "validation-next", status: "running" };
  const pendingForeground = deferred();
  validationApiMock.sources.mockResolvedValue([validationSource]);
  validationApiMock.runs.mockResolvedValueOnce([oldRun]).mockResolvedValue([nextRun]);
  validationApiMock.run.mockImplementation((runId) => {
    if (runId !== nextRun.id) return Promise.resolve(oldRun);
    return pendingForeground.promise;
  });
  const { result } = renderValidationController();

  await act(async () => result.current.loadValidation(validDraft.id));
  let foregroundLoad;
  await act(async () => {
    foregroundLoad = result.current.loadValidation(validDraft.id, nextRun.id);
    await Promise.resolve();
  });
  await waitFor(() => expect(validationApiMock.run).toHaveBeenCalledWith(nextRun.id));
  const sourceRequests = validationApiMock.sources.mock.calls.length;
  const runListRequests = validationApiMock.runs.mock.calls.length;
  let backgroundLoad;
  await act(async () => {
    backgroundLoad = result.current.loadValidation(validDraft.id, null, true);
    await Promise.resolve();
  });
  expect(validationApiMock.sources).toHaveBeenCalledTimes(sourceRequests);
  expect(validationApiMock.runs).toHaveBeenCalledTimes(runListRequests);
  await act(async () => {
    pendingForeground.resolve(nextRun);
    await Promise.all([foregroundLoad, backgroundLoad]);
  });
  expect(result.current.validationRuns).toEqual([nextRun]);
  expect(result.current.selectedValidation?.id).toBe(nextRun.id);
});

test("显式选择悬挂时轮询仍刷新用户期望的运行记录", async () => {
  const oldRun = { ...readyRun, id: "validation-old", status: "running" };
  const nextRun = { ...readyRun, id: "validation-next", status: "running" };
  const pendingSelection = deferred();
  validationApiMock.sources.mockResolvedValue([validationSource]);
  validationApiMock.runs.mockResolvedValueOnce([oldRun]).mockResolvedValue([nextRun]);
  validationApiMock.run.mockResolvedValue(oldRun);
  const { result } = renderValidationController();
  await act(async () => result.current.loadValidation(validDraft.id));
  validationApiMock.run
    .mockReturnValueOnce(pendingSelection.promise)
    .mockResolvedValueOnce(nextRun);

  let selectRequest;
  act(() => {
    selectRequest = result.current.selectValidation(nextRun.id);
  });
  await act(async () => result.current.loadValidation(validDraft.id, null, true));
  expect(validationApiMock.sources).toHaveBeenCalledTimes(2);
  expect(validationApiMock.runs).toHaveBeenCalledTimes(2);
  expect(result.current.validationRuns).toEqual([nextRun]);
  await waitFor(() => expect(result.current.selectedValidation?.id).toBe(nextRun.id));
  expect(validationApiMock.run).toHaveBeenLastCalledWith(nextRun.id);
  await act(async () => {
    pendingSelection.resolve(nextRun);
    await selectRequest;
  });
});

test("验证创建、审批和详情选择失败均恢复操作状态并提示", async () => {
  validationApiMock.sources.mockResolvedValue([validationSource]);
  validationApiMock.runs.mockResolvedValue([readyRun]);
  validationApiMock.start.mockRejectedValue(new Error("验证创建失败"));
  standardApiMock.approveClassificationStandardValidationRun.mockRejectedValue(
    new Error("验证审批失败"),
  );
  validationApiMock.run.mockRejectedValue(new Error("验证详情失败"));
  const { result, notify, setBusy } = renderValidationController();

  await act(async () => {
    await result.current.loadValidation(validDraft.id).catch(() => undefined);
  });
  expect(result.current.validationRuns).toEqual([readyRun]);
  await act(async () => result.current.startSampleValidation(null));
  await act(async () => result.current.approveSampleValidation(readyRun.id, "确认"));
  await act(async () => result.current.selectValidation(readyRun.id));

  expect(notify).toHaveBeenCalledWith("验证创建失败", "error");
  expect(notify).toHaveBeenCalledWith("验证审批失败", "error");
  expect(notify).toHaveBeenCalledWith("验证详情失败", "error");
  expect(setBusy.mock.calls).toEqual([["validation"], [""], ["approval"], [""]]);
});

test("轮询失败静默并在卸载时清理两秒定时器", async () => {
  const runningRun = { ...readyRun, id: "validation-running", status: "running" };
  const intervalCallbacks = [];
  vi.spyOn(window, "setInterval").mockImplementation((callback, delay) => {
    if (delay === 2000) intervalCallbacks.push(callback);
    return 91;
  });
  const clearIntervalSpy = vi.spyOn(window, "clearInterval");
  validationApiMock.sources.mockResolvedValue([validationSource]);
  validationApiMock.runs.mockResolvedValue([runningRun]);
  validationApiMock.run.mockResolvedValue(runningRun);
  const { result, unmount, notify } = renderValidationController();

  await act(async () => result.current.loadValidation(validDraft.id));
  await waitFor(() => expect(intervalCallbacks).toHaveLength(1));

  validationApiMock.sources.mockRejectedValueOnce(new Error("轮询失败"));
  intervalCallbacks.at(-1)();
  await waitFor(() => expect(validationApiMock.sources).toHaveBeenCalledTimes(2));
  expect(notify).not.toHaveBeenCalled();

  unmount();
  expect(clearIntervalSpy).toHaveBeenCalledWith(91);
});

test("质量门槛分开展示发布阻断项与人工复核警告", async () => {
  const { ClassificationValidationQuality } =
    await import("../src/features/classification-standards/ClassificationValidationQuality");
  const run = {
    items: [],
    summary: {},
    quality_gate: {
      status: "failed",
      passed: false,
      blocking: ["证据检查失败=1，要求不超过 0"],
      warnings: ["漏标实例=1，请人工复核"],
    },
  };

  render(<ClassificationValidationQuality run={run} />);

  const alert = screen.getByRole("alert");
  expect(within(alert).getByText("发布阻断项")).toBeVisible();
  expect(within(alert).getByText("证据检查失败=1，要求不超过 0")).toBeVisible();
  expect(within(alert).getByText("人工复核警告")).toBeVisible();
  expect(within(alert).getByText("漏标实例=1，请人工复核")).toBeVisible();
});

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
    await screen.findByRole("button", { name: /修改说明：创建替代标签/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "创建替代标签", exact: true }),
  );
  expect(screen.getByRole("textbox", { name: "标签编码 1" })).toHaveValue(
    "EYEWEAR_FIT_PRESSURE_V2",
  );
  await userEvent.clear(screen.getByRole("textbox", { name: "判定说明（可选） 1" }));
  await userEvent.type(
    screen.getByRole("textbox", { name: "判定说明（可选） 1" }),
    "明确描述鼻托压迫",
  );
  await userEvent.click(screen.getByRole("button", { name: "发布", exact: true }));
  const changeReason = screen.getByRole("textbox", { name: "变更说明" });
  await userEvent.clear(changeReason);
  await userEvent.type(changeReason, "明确鼻托压迫规则");
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
  expect(payload.change_reason).toBe("明确鼻托压迫规则");
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
  expect(screen.getByRole("button", { name: /^眼镜分类标准/ })).toBeVisible();
  expect(screen.getByText(formatDate(standard.updated_at))).toBeVisible();
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

test("分类标准搜索框保留原尺寸并只复位 AntD 内部输入框", () => {
  const styles = readFileSync(
    resolve(process.cwd(), "src/styles/classification-standards.css"),
    "utf8",
  );
  expect(styles).toMatch(
    /\.standard-library-toolbar > \.standard-search-box\s*{[^}]*height:\s*40px;/s,
  );
  expect(styles).toMatch(
    /\.label-directory \.standard-search-box\s*{[^}]*height:\s*36px;/s,
  );
  expect(styles).toMatch(
    /\.classification-standard-page[\s\S]*?\.standard-search-box\.ant-input-affix-wrapper[\s\S]*?> input\.ant-input\.ant-input\s*{[^}]*width:\s*100%;[^}]*min-width:\s*0;[^}]*min-height:\s*0;/s,
  );
  expect(styles).toMatch(
    /\.classification-standard-page[\s\S]*?\.standard-search-box\.ant-input-affix-wrapper[\s\S]*?> input\.ant-input:focus-visible\s*{[^}]*outline:\s*none;/s,
  );
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

  const partInput = screen.getByLabelText("新增证据部位编码");
  await userEvent.click(screen.getByRole("button", { name: "新增部位" }));
  expect(screen.getByText("请输入证据部位编码")).toBeVisible();
  expect(partInput).toHaveFocus();
  expect(partInput).toHaveAttribute("aria-invalid", "true");

  await userEvent.type(partInput, " ");
  expect(screen.queryByText("请输入证据部位编码")).not.toBeInTheDocument();
  await userEvent.type(partInput, "{Enter}");
  expect(screen.getByText("请输入证据部位编码")).toBeVisible();
  expect(partInput).toHaveFocus();

  await userEvent.clear(partInput);
  await userEvent.type(partInput, "knuckle_guard{Enter}");

  expect(screen.getAllByText("KNUCKLE_GUARD").length).toBeGreaterThan(0);
  expect(screen.queryByText("请输入证据部位编码")).not.toBeInTheDocument();
});

test("草稿校验显示字段错误并聚焦首个未填写字段", async () => {
  render(
    <ClassificationStandardsPage route={{ query: { view: "new" } }} notify={vi.fn()} />,
  );

  const nameInput = await screen.findByRole("textbox", { name: "标准名称" });
  const productContextInput = screen.getByRole("textbox", {
    name: "适用商品说明",
  });
  const categoryAInput = screen.getByRole("textbox", { name: "品类 A 1" });
  const categoryBInput = screen.getByRole("textbox", { name: "品类 B 1" });

  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  expect(await screen.findByText("请填写标准名称")).toBeVisible();
  expect(screen.getByText("请填写适用商品说明")).toBeVisible();
  expect(screen.getByText("请填写品类 A")).toBeVisible();
  expect(screen.getByText("请填写品类 B")).toBeVisible();
  expect(nameInput).toHaveFocus();
  expect(nameInput).toHaveAttribute("aria-invalid", "true");
  expect(nameInput).toHaveAccessibleDescription("请填写标准名称");

  await userEvent.type(nameInput, "背包分类标准");
  expect(screen.queryByText("请填写标准名称")).not.toBeInTheDocument();
  expect(screen.getByText("请填写适用商品说明")).toBeVisible();
  expect(nameInput).toHaveAttribute("aria-invalid", "false");

  await userEvent.type(productContextInput, "户外背包");
  expect(screen.queryByText("请填写适用商品说明")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  expect(categoryAInput).toHaveFocus();
  expect(categoryAInput).toHaveAccessibleDescription("请填写品类 A");

  await userEvent.type(categoryAInput, "箱包");
  expect(screen.queryByText("请填写品类 A")).not.toBeInTheDocument();
  expect(screen.getByText("请填写品类 B")).toBeVisible();
  expect(categoryBInput).toHaveAttribute("aria-invalid", "true");
  expect(standardApiMock.createClassificationStandard).not.toHaveBeenCalled();
});

test("草稿没有标签时就近提示并聚焦创建入口", async () => {
  render(
    <ClassificationStandardsPage route={{ query: { view: "new" } }} notify={vi.fn()} />,
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
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));

  expect(await screen.findByText("请至少增加一个分类标签")).toBeVisible();
  const createButton = screen.getByRole("button", { name: "创建第一个标签" });
  await waitFor(() => expect(createButton).toHaveFocus());
  expect(createButton).toHaveAccessibleDescription("请至少增加一个分类标签");

  await userEvent.click(createButton);
  expect(screen.queryByText("请至少增加一个分类标签")).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "标签名称 1" })).toBeVisible();
});

test("同次校验清除标签错误时保持用户选择的标签分区", async () => {
  render(
    <ClassificationStandardsPage route={{ query: { view: "new" } }} notify={vi.fn()} />,
  );

  await screen.findByRole("textbox", { name: "标准名称" });
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  expect(screen.getByRole("textbox", { name: "标准名称" })).toHaveFocus();

  const labelsTab = screen.getByRole("button", {
    name: "标签管理",
    exact: true,
  });
  await userEvent.click(labelsTab);
  await userEvent.click(screen.getByRole("button", { name: "创建第一个标签" }));

  expect(labelsTab).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("textbox", { name: "标签名称 1" })).toBeVisible();
  expect(screen.queryByText("请至少增加一个分类标签")).not.toBeInTheDocument();
});

test("标签校验显示字段错误并只清除已修改字段", async () => {
  const invalidDraft = {
    ...draft,
    content: {
      ...content,
      labels: [
        {
          code: "",
          name: "",
          group: "",
          description: "",
          keywords: [],
          allowed_sentiments: ["NEGATIVE"],
          allowed_claim_ids: [],
        },
      ],
    },
  };
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: invalidDraft.id,
    draft_revision: invalidDraft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(invalidDraft);

  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );

  const nameInput = await screen.findByRole("textbox", { name: "标签名称 1" });
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  expect(await screen.findByText("请填写标签名称")).toBeVisible();
  expect(screen.getByText("请选择标签分组")).toBeVisible();
  expect(screen.getByText("请填写标签编码")).toBeVisible();
  expect(screen.queryByText("请填写业务定义")).not.toBeInTheDocument();
  await waitFor(() => expect(nameInput).toHaveFocus());
  expect(nameInput).toHaveAccessibleDescription("请填写标签名称");

  await userEvent.type(nameInput, "结构损坏");
  expect(screen.queryByText("请填写标签名称")).not.toBeInTheDocument();
  expect(screen.getByText("请选择标签分组")).toBeVisible();
  expect(screen.getByRole("combobox", { name: "标签分组 1" })).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(standardApiMock.updateClassificationStandardDraft).not.toHaveBeenCalled();
});

test("已发布标签的编码和语义不可直接修改", async () => {
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id, view: "edit" } }}
      notify={vi.fn()}
    />,
  );

  expect(await screen.findByRole("complementary", { name: "标签目录" })).toBeVisible();
  for (const name of ["标签分组 1", "标签名称 1", "标签编码 1", "判定说明（可选） 1"])
    expect(screen.queryByRole("textbox", { name })).toBeNull();
  expect(screen.getByText("镜框或镜腿造成压迫")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "搜索别名 1" })).toBeEnabled();
  expect(screen.getByRole("button", { name: /修改说明：创建替代标签/ })).toBeVisible();
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
  const validationRegion = await screen.findByRole("region", {
    name: "发布前样本验证",
  });
  expect(validationRegion.closest("details")).toBeNull();
  expect(within(validationRegion).getByText("必需")).toBeVisible();
  expect(await screen.findByRole("button", { name: "等待样本验证" })).toBeDisabled();
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("草稿保存失败后保留未保存内容并恢复操作状态", async () => {
  mockEditableDraft();
  standardApiMock.updateClassificationStandardDraft.mockRejectedValue(
    new Error("草稿保存冲突"),
  );
  const notify = renderEditPage();
  await userEvent.click(
    await screen.findByRole("button", { name: "标准设置", exact: true }),
  );
  const nameInput = screen.getByRole("textbox", { name: "标准名称" });
  await userEvent.clear(nameInput);
  await userEvent.type(nameInput, "保存失败仍保留的标准名称");
  await userEvent.click(screen.getByRole("button", { name: "保存草稿" }));

  await waitFor(() => expect(notify).toHaveBeenCalledWith("草稿保存冲突", "error"));
  expect(nameInput).toHaveValue("保存失败仍保留的标准名称");
  expect(screen.getByRole("button", { name: "保存草稿" })).toBeEnabled();
  expect(standardApiMock.validateClassificationStandardDraft).not.toHaveBeenCalled();
});

test("发布失败后保留变更说明并恢复发布操作状态", async () => {
  mockEditableDraft({ runs: [readyRun] });
  standardApiMock.publishClassificationStandardDraft.mockRejectedValue(
    new Error("发布版本冲突"),
  );
  const notify = renderEditPage();
  await openPublishReview();
  const reasonInput = screen.getByRole("textbox", { name: "变更说明" });
  await userEvent.clear(reasonInput);
  await userEvent.type(reasonInput, "发布失败后继续使用的说明");
  await userEvent.click(screen.getByRole("button", { name: "发布并启用" }));

  await waitFor(() =>
    expect(standardApiMock.publishClassificationStandardDraft).toHaveBeenCalledWith(
      validDraft.id,
      {
        expected_revision: validDraft.revision,
        reason: "发布失败后继续使用的说明",
      },
    ),
  );
  expect(notify).toHaveBeenCalledWith("发布版本冲突", "error");
  expect(reasonInput).toHaveValue("发布失败后继续使用的说明");
  expect(screen.getByRole("button", { name: "发布并启用" })).toBeEnabled();
});

test("编辑页加载验证来源与运行记录并允许选择另一条记录", async () => {
  const previousRun = {
    ...readyRun,
    id: "classification-standard-validation-previous",
    draft_revision: 1,
    is_current: false,
    publication_ready: false,
  };
  mockEditableDraft({ sources: [validationSource], runs: [readyRun, previousRun] });
  validationApiMock.run.mockImplementation(async (runId) =>
    runId === previousRun.id ? previousRun : readyRun,
  );
  renderEditPage();
  await waitFor(() => {
    expect(validationApiMock.sources).toHaveBeenCalledWith(validDraft.id);
    expect(validationApiMock.runs).toHaveBeenCalledWith(validDraft.id);
    expect(validationApiMock.run).toHaveBeenCalledWith(readyRun.id);
  });
  await openPublishReview();
  expect(screen.getByRole("combobox", { name: "样本来源" })).toHaveValue(
    validationSource.result_version_id,
  );
  await userEvent.click(
    screen.getByRole("button", {
      name: /验证完成.*草稿 r1.*20\/20 条.*已失效/,
    }),
  );

  await waitFor(() =>
    expect(validationApiMock.run).toHaveBeenLastCalledWith(previousRun.id),
  );
  expect(screen.getByRole("heading", { name: "草稿 r1 验证结果" })).toBeVisible();
});

test("仅在验证运行中轮询并在运行完成后停止", async () => {
  const runningRun = {
    ...readyRun,
    id: "classification-standard-validation-running",
    status: "running",
    processed_count: 5,
    publication_ready: false,
    approved_by_name: null,
    approved_at: null,
    approval_note: "",
  };
  const completedRun = {
    ...runningRun,
    status: "completed",
    processed_count: 20,
  };
  const validationPolls = [];
  const setIntervalSpy = vi
    .spyOn(window, "setInterval")
    .mockImplementation((callback, delay) => {
      if (delay === 2000) validationPolls.push(callback);
      return 73;
    });
  mockEditableDraft();
  validationApiMock.runs
    .mockResolvedValueOnce([runningRun])
    .mockResolvedValueOnce([completedRun]);
  validationApiMock.run
    .mockResolvedValueOnce(runningRun)
    .mockResolvedValueOnce(completedRun);

  try {
    renderEditPage();
    await waitFor(() => expect(validationPolls).toHaveLength(1));
    expect(validationApiMock.runs).toHaveBeenCalledTimes(1);

    await act(async () => {
      validationPolls[0]();
    });

    await waitFor(() => expect(validationApiMock.runs).toHaveBeenCalledTimes(2));
    expect(validationApiMock.run).toHaveBeenLastCalledWith(runningRun.id);
    await screen.findByText("草稿 r2 验证结果");
    expect(validationPolls).toHaveLength(1);
  } finally {
    setIntervalSpy.mockRestore();
  }
});

test("开始样本验证提交当前草稿修订、来源、规模和验证目的", async () => {
  const queuedRun = {
    ...readyRun,
    id: "classification-standard-validation-queued",
    status: "queued",
    processed_count: 0,
    publication_ready: false,
    approved_by_name: null,
    approved_at: null,
    approval_note: "",
  };
  mockEditableDraft({ sources: [validationSource] });
  validationApiMock.start.mockResolvedValue(queuedRun);
  validationApiMock.run.mockResolvedValue(queuedRun);
  const notify = renderEditPage();
  await openPublishReview();
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "验证目的" }),
    "semantic_ab",
  );
  await userEvent.click(screen.getByRole("button", { name: "50 条" }));
  await userEvent.click(screen.getByRole("button", { name: "开始样本验证" }));

  await waitFor(() =>
    expect(validationApiMock.start).toHaveBeenCalledWith(validDraft.id, {
      expected_revision: validDraft.revision,
      source_result_version_id: validationSource.result_version_id,
      sample_size: 50,
      comparison_type: "semantic_ab",
    }),
  );
  expect(validationApiMock.run).toHaveBeenLastCalledWith(queuedRun.id);
  expect(notify).toHaveBeenCalledWith("样本验证已进入队列");
});

test("原始数据验证完成后必须人工确认才能发布", async () => {
  const notify = vi.fn();
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
    draft_revision: validDraft.revision,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(validDraft);
  standardApiMock.classificationStandardValidationSources.mockResolvedValue([
    validationSource,
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
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "样本来源" }),
    validationSource.result_version_id,
  );
  expect(screen.getByRole("option", { name: /真实手套退货评论/ })).toBeInTheDocument();
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
    screen.getByRole("textbox", { name: "判定说明（可选） 1" }),
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

  const deactivate = await screen.findByRole("button", {
    name: `停用标准：${standard.name}`,
  });
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
    {
      ...standard,
      id: "unpublished",
      name: "未发布标准",
      status: "inactive",
      version_no: 0,
      delete_mode: "delete",
    },
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
  const onSampleSizeChange = vi.fn();
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
      onSampleSizeChange={onSampleSizeChange}
    />,
  );
  const button = screen.getByRole("button", { name: "开始样本验证" });
  expect(button).toBeDisabled();
  expect(screen.getByText("请选择 Review 表格后开始验证。")).toBeVisible();
  expect(button).toHaveAttribute(
    "aria-describedby",
    "standard-validation-disabled-reason",
  );
  expect(screen.getByText("导入人工参考答案（可选）").closest("label")).toBeNull();
  const file = new File(["test"], "reviews.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const fileInput = screen.getByLabelText("Review 表格");
  expect(fileInput).toHaveAttribute(
    "aria-describedby",
    "standard-validation-review-file-help",
  );
  await userEvent.upload(fileInput, file);
  expect(button).toBeEnabled();
  expect(screen.queryByText("请选择 Review 表格后开始验证。")).toBeNull();
  expect(button).not.toHaveAttribute("aria-describedby");
  await userEvent.click(screen.getByRole("button", { name: "50 条" }));
  expect(onSampleSizeChange).toHaveBeenCalledWith(50);
  await userEvent.click(button);
  expect(onRun).toHaveBeenCalledWith(file, "standard_version");
});

test("样本验证按钮解释当前优先禁用原因", async () => {
  const { ClassificationStandardValidation } =
    await import("../src/features/classification-standards/ClassificationStandardValidation");
  const commonProps = {
    sources: [],
    selectedRun: null,
    sourceId: "",
    sampleSize: 20,
    busy: false,
    approvalBusy: false,
    dirty: false,
    onRun: vi.fn(),
    onApprove: vi.fn(),
    onSelectRun: vi.fn(),
    onSourceChange: vi.fn(),
    onSampleSizeChange: vi.fn(),
  };
  const { rerender } = render(
    <ClassificationStandardValidation
      {...commonProps}
      draft={{ validation: { blocking: ["标签编码重复"] } }}
      runs={[]}
    />,
  );
  expect(screen.getByText("请先解决结构检查中的阻断项。")).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "请先解决结构检查中的阻断项，再运行样本验证。",
  );

  rerender(
    <ClassificationStandardValidation
      {...commonProps}
      draft={{ validation: { blocking: [] } }}
      runs={[
        {
          id: "running-validation",
          status: "running",
          draft_revision: 2,
          processed_count: 4,
          sample_size: 20,
          is_current: true,
        },
      ]}
    />,
  );
  expect(screen.getByText("已有样本验证正在运行，请等待完成。")).toBeVisible();
});

test("发布前样本验证在目标宽度使用三段响应式布局", () => {
  const styles = readFileSync(
    resolve(process.cwd(), "src/styles/classification-standards.css"),
    "utf8",
  );
  expect(styles).toMatch(
    /\.standard-validation-configuration\s*{[^}]*grid-template-columns:\s*repeat\(2, minmax\(220px, 1fr\)\) auto;/s,
  );
  expect(styles).toMatch(
    /@media \(max-width:\s*1100px\)[\s\S]*?\.standard-validation-configuration\s*{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\);/,
  );
  expect(styles).toMatch(
    /@media \(max-width:\s*900px\)[\s\S]*?\.standard-validation-configuration,[\s\S]*?\.standard-review-upload,[\s\S]*?\.standard-validation-actions\s*{[^}]*grid-template-columns:\s*minmax\(0, 1fr\);/,
  );
  expect(styles).toMatch(
    /@media \(max-width:\s*900px\)[\s\S]*?\.standard-validation-actions \.primary-button\s*{[^}]*width:\s*100%;[^}]*min-width:\s*0;/,
  );
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

test("结构检查定位缺名称和方向的标签，规则修正只写草稿", async () => {
  const imported = {
    ...content,
    structure_version: 2,
    categories: [
      { code: "ROOT", name: "尺码" },
      { code: "FIT", name: "不合身", parent_code: "ROOT" },
    ],
    validation_rules: { neutral_reason_labels: ["OLD_LABEL"] },
    labels: [
      {
        ...content.labels[0],
        code: "NEW_SMALL",
        name: "偏小",
        group: "尺码",
        parent_code: "FIT",
        description: "",
        allowed_sentiments: [],
      },
    ],
  };
  const issues = [
    {
      kind: "missing_field",
      message: "请填写标签名称",
      label_code: "NEW_SMALL",
      label_index: 0,
      field: "name",
    },
    {
      kind: "missing_sentiment",
      message: "请确认评价方向",
      label_code: "NEW_SMALL",
      label_index: 0,
      field: "allowed_sentiments",
    },
    {
      kind: "invalid_rule",
      message: "校验规则引用未知标签 OLD_LABEL",
      field: "validation_rules",
    },
  ];
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue({
    ...validDraft,
    content: imported,
    validation: { blocking: issues.map((item) => item.message), warnings: [], issues },
  });
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_, payload) => ({ ...validDraft, content: payload.content }),
  );
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "发布", exact: true }),
  );
  const region = screen.getByRole("region", { name: "结构检查" });
  expect(within(region).getByText("必填信息不完整 · 1 项")).toBeVisible();
  expect(within(region).getByText("评价方向待确认 · 1 项")).toBeVisible();
  await userEvent.click(
    within(region).getAllByRole("button", { name: "去修正 尺码 → 不合身 → 偏小" })[0],
  );
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "标签名称 1" })).toHaveFocus(),
  );
  await userEvent.click(screen.getByRole("button", { name: "发布", exact: true }));
  await userEvent.click(
    within(region).getAllByRole("button", { name: "去修正 尺码 → 不合身 → 偏小" })[1],
  );
  await waitFor(() =>
    expect(screen.getByRole("checkbox", { name: "负向", exact: true })).toHaveFocus(),
  );
  await userEvent.click(screen.getByRole("button", { name: "发布", exact: true }));
  await userEvent.click(
    screen.getByRole("button", { name: "去修正 校验规则引用未知标签 OLD_LABEL" }),
  );
  expect(screen.getByRole("heading", { name: "标签校验规则" })).toHaveFocus();
  await userEvent.click(
    screen.getByRole("button", { name: "删除中性退货原因规则 OLD_LABEL" }),
  );
  expect(standardApiMock.updateClassificationStandardDraft).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "保存草稿", exact: true }));
  await waitFor(() =>
    expect(standardApiMock.updateClassificationStandardDraft).toHaveBeenCalled(),
  );
  expect(
    standardApiMock.updateClassificationStandardDraft.mock.calls[0][1].content
      .validation_rules.neutral_reason_labels,
  ).toEqual([]);
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("未改动的旧草稿保存时重新结构检查而不增加修订", async () => {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue(validDraft);
  const message = "请填写标签名称";
  standardApiMock.validateClassificationStandardDraft.mockResolvedValue({
    ...validDraft,
    validation: {
      blocking: [message],
      warnings: [],
      issues: [
        {
          kind: "missing_field",
          message,
          label_code: content.labels[0].code,
          field: "name",
        },
      ],
    },
  });
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "保存草稿", exact: true }),
  );
  await waitFor(() =>
    expect(standardApiMock.validateClassificationStandardDraft).toHaveBeenCalledWith(
      validDraft.id,
      validDraft.revision,
    ),
  );
  expect(standardApiMock.updateClassificationStandardDraft).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "发布", exact: true }));
  expect(screen.getByText("必填信息不完整 · 1 项")).toBeVisible();
});

test("不能定位的结构问题仅展示说明，失效规则保留修正入口", () => {
  const validation = {
    blocking: ["标准无差异", "规则失效"],
    issues: [
      { kind: "invalid_structure", message: "标准无差异" },
      { kind: "invalid_rule", message: "规则失效" },
    ],
  };
  render(
    <ClassificationStructureIssues
      validation={validation}
      content={content}
      onFix={vi.fn()}
    />,
  );
  expect(screen.getByText("标准无差异")).toBeVisible();
  expect(screen.queryByRole("button", { name: "去修正 标准无差异" })).toBeNull();
  expect(screen.getByRole("button", { name: "去修正 规则失效" })).toBeVisible();
});

test.each([1, 2])("v%s 标签可以清空判定说明并保存草稿", async (structureVersion) => {
  const editableContent = {
    ...content,
    structure_version: structureVersion,
    ...(structureVersion === 2
      ? { categories: [{ code: "FIT", name: "尺码与适配" }] }
      : {}),
    labels: [
      {
        ...content.labels[0],
        code: "NEW_FIT",
        parent_code: structureVersion === 2 ? "FIT" : undefined,
      },
    ],
  };
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    draft_id: validDraft.id,
  });
  standardApiMock.classificationStandardDraft.mockResolvedValue({
    ...validDraft,
    content: editableContent,
  });
  standardApiMock.updateClassificationStandardDraft.mockImplementation(
    async (_, payload) => ({ ...validDraft, content: payload.content }),
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
  const description = await screen.findByRole("textbox", {
    name: "判定说明（可选） 1",
  });
  await userEvent.clear(description);
  await userEvent.click(screen.getByRole("button", { name: "保存草稿", exact: true }));
  await waitFor(() =>
    expect(standardApiMock.updateClassificationStandardDraft).toHaveBeenCalled(),
  );
  expect(
    standardApiMock.updateClassificationStandardDraft.mock.calls[0][1].content.labels[0]
      .description,
  ).toBe("");
  expect(standardApiMock.validateClassificationStandardDraft).toHaveBeenCalled();
  expect(screen.getByRole("textbox", { name: "判定说明（可选） 1" })).toHaveValue("");
  expect(standardApiMock.publishClassificationStandardDraft).not.toHaveBeenCalled();
});

test("没有判定说明的已发布标签展示名称路径语义提示", async () => {
  standardApiMock.classificationStandard.mockResolvedValue({
    ...detail,
    snapshot: {
      ...snapshot,
      taxonomy: {
        ...snapshot.taxonomy,
        labels: [{ ...content.labels[0], description: "" }],
      },
    },
  });
  render(
    <ClassificationStandardsPage
      route={{ query: { standard: standard.id } }}
      notify={vi.fn()}
    />,
  );
  expect(await screen.findByText("依据标签名称和完整路径理解")).toBeVisible();
  expect(screen.getByText("尺码与适配 → 佩戴压迫")).toBeVisible();
});
