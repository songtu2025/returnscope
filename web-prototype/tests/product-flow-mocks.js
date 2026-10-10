import { beforeEach, afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    mysqlReturnSchema: vi.fn(),
    me: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    status: vi.fn(),
    tasks: vi.fn(),
    task: vi.fn(),
    archiveTasks: vi.fn(),
    preflightTask: vi.fn(),
    preflightTaskReplan: vi.fn(),
    replanTask: vi.fn(),
    resumeTask: vi.fn(),
    retryTaskSegment: vi.fn(),
    retrySegmentResultPublish: vi.fn(),
    reorderTaskSegments: vi.fn(),
    controlTaskSegment: vi.fn(),
    setTaskParallelism: vi.fn(),
    analysis: vi.fn(),
    analysisDownloadUrl: vi.fn(),
    taskEvents: vi.fn(),
    eventUrl: vi.fn(),
    downloadUrl: vi.fn(),
    segmentDownloadUrl: vi.fn(),
    classificationResultDownloadUrl: vi.fn(),
    classificationResults: vi.fn(),
    datasets: vi.fn(),
    dataset: vi.fn(),
    datasetRows: vi.fn(),
    dataVersionReferences: vi.fn(),
    datasetDownloadUrl: vi.fn(),
    completeProductCategories: vi.fn(),
    dataVersions: vi.fn(),
    qualityPreflight: vi.fn(),
    productScopes: vi.fn(),
    createDataset: vi.fn(),
    addDatasetVersion: vi.fn(),
    inspectReturnImport: vi.fn(),
    importReturns: vi.fn(),
    configs: vi.fn(),
    activeValidation: vi.fn(),
    startModelValidation: vi.fn(),
    validationEventUrl: vi.fn(),
    validationRun: vi.fn(),
    reviews: vi.fn(),
    review: vi.fn(),
    reviewTaxonomy: vi.fn(),
    taxonomy: vi.fn(),
    resolveReview: vi.fn(),
    createTask: vi.fn(),
    createConfig: vi.fn(),
    discardConfig: vi.fn(),
    createModel: vi.fn(),
    discoverModels: vi.fn(),
    updateModel: vi.fn(),
    publishConfig: vi.fn(),
    startConfigValidation: vi.fn(),
    modelPreference: vi.fn(),
    saveModelPreference: vi.fn(),
    users: vi.fn(),
    invitations: vi.fn(),
    inviteUser: vi.fn(),
    resendInvitation: vi.fn(),
    revokeInvitation: vi.fn(),
    validateInvitation: vi.fn(),
    register: vi.fn(),
    requestPasswordReset: vi.fn(),
    validatePasswordReset: vi.fn(),
    completePasswordReset: vi.fn(),
    requestEmailChange: vi.fn(),
    validateEmailChange: vi.fn(),
    completeEmailChange: vi.fn(),
    changePassword: vi.fn(),
    updateUserStatus: vi.fn(),
  },
}));

vi.mock("../src/api", () => ({
  api: apiMock,
  ApiError: class ApiError extends Error {},
}));

vi.mock("../src/shared/api/modelApi", () => ({ modelApi: apiMock }));

vi.mock("../src/shared/api/taskApi", () => ({
  taskApi: { tasks: apiMock.tasks },
}));

vi.mock("../src/shared/api/resultApi", () => ({
  resultApi: { classificationResults: apiMock.classificationResults },
}));

const systemStatus = {
  worker_status: "ok",
  my_running_tasks: 0,
  pending_reviews: 1,
  task_counts: {},
  warnings: [],
};

export const executionPlan = {
  registry_version: "category-capabilities-v1",
  plan_hash: "a".repeat(64),
  scope_mode: "auto",
  primary_store: "SEEKWAY:US",
  detected_scopes: [
    {
      store: "SEEKWAY:US",
      listing: "SK001",
      record_count: 12,
      unique_comments: 8,
    },
  ],
  unresolved_scope_count: 0,
  unresolved_scope_record_count: 0,
  record_count: 12,
  valid_comment_count: 10,
  unique_comment_count: 8,
  executable_count: 8,
  executable_record_count: 12,
  blocked_count: 0,
  blocked_record_count: 0,
  missing_category_count: 0,
  missing_category_record_count: 0,
  missing_categories: [],
  unknown_category_count: 0,
  unknown_category_record_count: 0,
  unknown_categories: [],
  segments: [
    {
      segment_key: "footwear",
      agent_key: "footwear",
      agent_family: "鞋履智能体",
      scope: { store: "SEEKWAY:US", listing: "SK001" },
      logic_version: "footwear-v2",
      taxonomy_version: "taxonomy-v3",
      record_count: 12,
      unique_comments: 8,
      status: "ready",
      variants: [
        {
          category_a: "鞋履",
          category_b: "薄底水鞋",
          record_count: 12,
          unique_comments: 8,
        },
      ],
    },
  ],
};

beforeEach(() => {
  window.scrollTo = vi.fn();
  window.location.hash = "";
  Object.values(apiMock).forEach((mock) => mock.mockReset());
  apiMock.mysqlReturnSchema.mockResolvedValue({ configured: false });
  apiMock.status.mockResolvedValue(systemStatus);
  apiMock.tasks.mockResolvedValue([]);
  apiMock.classificationResults.mockResolvedValue({ items: [], total: 0 });
  apiMock.datasets.mockResolvedValue([]);
  apiMock.datasetRows.mockResolvedValue({ records: [], total: 0 });
  apiMock.reviews.mockResolvedValue([]);
  apiMock.configs.mockResolvedValue([]);
  apiMock.modelPreference.mockResolvedValue(null);
  apiMock.dataVersions.mockResolvedValue([]);
  apiMock.qualityPreflight.mockResolvedValue({
    counts: {
      total_records: 12,
      matched_records: 12,
      unmatched_records: 0,
    },
  });
  apiMock.productScopes.mockResolvedValue([]);
  apiMock.taxonomy.mockResolvedValue({ labels: [] });
  apiMock.reviewTaxonomy.mockResolvedValue({ labels: [] });
  apiMock.activeValidation.mockResolvedValue(null);
  apiMock.users.mockResolvedValue([]);
  apiMock.invitations.mockResolvedValue([]);
  apiMock.eventUrl.mockReturnValue("/events");
  apiMock.validationEventUrl.mockReturnValue("/validation-events");
  apiMock.analysisDownloadUrl.mockReturnValue("/analysis-download");
  apiMock.segmentDownloadUrl.mockReturnValue("/segment-download");
  apiMock.classificationResultDownloadUrl.mockReturnValue("/classification-download");
  apiMock.preflightTask.mockResolvedValue(executionPlan);
});

afterEach(() => cleanup());

export { apiMock };
