import { groups as BUSINESS_GROUPS } from "../../../../config/taxonomy_alignment.json";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpenText,
  CheckCircle,
  ClockCounterClockwise,
  DownloadSimple,
  MagnifyingGlass,
  Plus,
  Tag,
  UploadSimple,
} from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, Modal, PageHeading } from "../../components/SharedUi";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { ClassificationStandardEditor } from "./ClassificationStandardDraftEditor";
import { ClassificationStandardValidation } from "./ClassificationStandardValidation";
import { labelChanges } from "./labelDraftPolicy";

const clone = (value) => JSON.parse(JSON.stringify(value));

const EMPTY_CONTENT = {
  recognition_profile: "semantic_v1",
  name: "",
  product_context: "",
  instructions: ["依据标签业务定义判断退货原因"],
  allowed_parts: ["UNSPECIFIED"],
  validation_rules: {
    allowed_groups: BUSINESS_GROUPS,
    neutral_reason_labels: [],
    conflict_scope: "evidence",
  },
  variants: [{ category_a: "", category_b: "", attributes: {} }],
  labels: [],
};

function contentFromSnapshot(snapshot) {
  return {
    name: snapshot.name,
    recognition_profile: snapshot.taxonomy.recognition_profile ?? "legacy_v3",
    product_context: snapshot.taxonomy.product_context,
    instructions: snapshot.taxonomy.instructions ?? [],
    allowed_parts: snapshot.taxonomy.allowed_parts ?? ["UNSPECIFIED"],
    validation_rules: snapshot.taxonomy.validation_rules ?? {},
    variants: snapshot.variants ?? [],
    labels: (snapshot.taxonomy.labels ?? []).map((label) => ({
      ...label,
      keywords: label.keywords ?? [],
    })),
  };
}

function statusLabel(standard) {
  if (standard.status === "active") return "使用中";
  return Number(standard.version_no) > 0 ? "已停用" : "未发布";
}

function formatDate(value) {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("zh-CN");
}

function validateContent(content) {
  if (!content.name.trim() || !content.product_context.trim()) {
    return "请填写标准名称和适用商品说明";
  }
  if (
    content.variants.length === 0 ||
    content.variants.some((item) => !item.category_a.trim() || !item.category_b.trim())
  ) {
    return "请完整填写适用品类";
  }
  if (content.labels.length === 0) return "请至少增加一个分类标签";
  if (
    content.labels.some(
      (item) =>
        !item.code.trim() ||
        !item.name.trim() ||
        !item.group.trim() ||
        !item.description.trim(),
    )
  ) {
    return "请完整填写标签分组、名称、编码和业务定义";
  }
  return "";
}

export function ClassificationStandardsPage({ route, notify }) {
  const [standards, setStandards] = useState([]);
  const [detail, setDetail] = useState(null);
  const [versions, setVersions] = useState([]);
  const [draft, setDraft] = useState(null);
  const [content, setContent] = useState(clone(EMPTY_CONTENT));
  const [changeReason, setChangeReason] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);
  const [busy, setBusy] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [restoreTarget, setRestoreTarget] = useState(null);
  const [validationSources, setValidationSources] = useState([]);
  const [validationRuns, setValidationRuns] = useState([]);
  const [selectedValidation, setSelectedValidation] = useState(null);
  const [validationSourceId, setValidationSourceId] = useState("");
  const [validationSampleSize, setValidationSampleSize] = useState(20);

  const selectedId = route.query.standard || "";
  const mode = route.query.view === "new" ? "new" : selectedId ? "edit" : "list";

  const loadStandards = useCallback(async () => {
    const values = await classificationStandardApi.classificationStandards();
    setStandards(values);
    return values;
  }, []);

  const loadValidation = useCallback(async (draftId, preferredRunId = null) => {
    const [sources, runs] = await Promise.all([
      classificationStandardApi.classificationStandardValidationSources(draftId),
      classificationStandardApi.classificationStandardValidationRuns(draftId),
    ]);
    setValidationSources(sources);
    setValidationRuns(runs);
    setValidationSourceId((current) =>
      sources.some((source) => source.result_version_id === current)
        ? current
        : sources[0]?.result_version_id || "",
    );
    const selectedRunId = preferredRunId || runs[0]?.id;
    setSelectedValidation(
      selectedRunId
        ? await classificationStandardApi.classificationStandardValidationRun(
            selectedRunId,
          )
        : null,
    );
  }, []);

  const loadSelected = useCallback(
    async (standardId) => {
      setPageLoading(true);
      try {
        const [standard, versionRows] = await Promise.all([
          classificationStandardApi.classificationStandard(standardId),
          classificationStandardApi.classificationStandardVersions(standardId),
        ]);
        const draftValue = standard.draft_id
          ? await classificationStandardApi.classificationStandardDraft(
              standard.draft_id,
            )
          : null;
        setDetail(standard);
        setVersions(versionRows);
        setDraft(draftValue);
        setContent(
          clone(draftValue?.content ?? contentFromSnapshot(standard.snapshot)),
        );
        setChangeReason(draftValue?.change_reason || `更新${standard.name}`);
        if (draftValue) await loadValidation(draftValue.id);
        else {
          setValidationSources([]);
          setValidationRuns([]);
          setSelectedValidation(null);
          setValidationSourceId("");
        }
      } finally {
        setPageLoading(false);
      }
    },
    [loadValidation],
  );

  useEffect(() => {
    loadStandards()
      .catch((error) => notify(error.message, "error"))
      .finally(() => setLoading(false));
  }, [loadStandards, notify]);

  useEffect(() => {
    if (mode === "new") {
      setDetail(null);
      setVersions([]);
      setDraft(null);
      setContent(clone(EMPTY_CONTENT));
      setChangeReason("新增分类标准");
      return;
    }
    if (!selectedId) return;
    loadSelected(selectedId).catch((error) => notify(error.message, "error"));
  }, [loadSelected, mode, notify, selectedId]);

  useEffect(() => {
    const active = validationRuns.some((run) =>
      ["queued", "running"].includes(run.status),
    );
    if (!draft || !active) return undefined;
    const timer = window.setInterval(() => {
      loadValidation(draft.id, selectedValidation?.id).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [draft, loadValidation, selectedValidation?.id, validationRuns]);

  const filteredStandards = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return standards.filter((standard) => {
      const matchesStatus = statusFilter === "all" || standard.status === statusFilter;
      const text =
        `${standard.name} ${standard.product_context} ${standard.agent_family}`.toLowerCase();
      return matchesStatus && (!keyword || text.includes(keyword));
    });
  }, [query, standards, statusFilter]);

  const totals = useMemo(
    () => ({
      active: standards.filter((item) => item.status === "active").length,
      categories: standards
        .filter((item) => item.status === "active")
        .reduce((sum, item) => sum + item.category_count, 0),
      labels: standards
        .filter((item) => item.status === "active")
        .reduce((sum, item) => sum + item.label_count, 0),
    }),
    [standards],
  );

  const savedContent =
    draft?.content ??
    (detail?.snapshot ? contentFromSnapshot(detail.snapshot) : EMPTY_CONTENT);
  const dirty = JSON.stringify(content) !== JSON.stringify(savedContent);

  useEffect(() => {
    if (!dirty || !["edit", "new"].includes(mode)) return;
    const warnBeforeClose = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeClose);
    return () => window.removeEventListener("beforeunload", warnBeforeClose);
  }, [dirty, mode]);

  const persistDraft = async () => {
    const error = validateContent(content);
    if (error) throw new Error(error);

    let workingDraft = draft;
    if (!workingDraft) {
      if (mode === "new") {
        const firstCategory = content.variants[0];
        workingDraft = await classificationStandardApi.createClassificationStandard({
          name: content.name.trim(),
          product_context: content.product_context.trim(),
          category_a: firstCategory.category_a.trim(),
          category_b: firstCategory.category_b.trim(),
        });
      } else {
        workingDraft =
          await classificationStandardApi.createClassificationStandardDraft(detail.id);
      }
    }

    if (JSON.stringify(content) !== JSON.stringify(workingDraft.content)) {
      workingDraft = await classificationStandardApi.updateClassificationStandardDraft(
        workingDraft.id,
        {
          expected_revision: workingDraft.revision,
          content,
          change_reason: changeReason.trim(),
        },
      );
    }
    setDraft(workingDraft);
    setContent(clone(workingDraft.content));
    return workingDraft;
  };

  const saveDraft = async () => {
    setBusy("save");
    try {
      const saved = await persistDraft();
      await loadStandards();
      await loadValidation(saved.id);
      if (mode === "new") {
        navigateHash(
          "classification-standards",
          { standard: saved.standard_id, view: "edit" },
          { replace: true },
        );
      }
      notify("修改已保存");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const publish = async () => {
    setBusy("publish");
    try {
      const saved = await persistDraft();
      if (saved.validation.blocking.length > 0) {
        throw new Error(saved.validation.blocking.join("；"));
      }
      const standard =
        await classificationStandardApi.publishClassificationStandardDraft(saved.id, {
          expected_revision: saved.revision,
          reason: changeReason.trim() || "更新分类标准",
        });
      await loadStandards();
      await loadSelected(standard.id);
      navigateHash("classification-standards", { standard: standard.id });
      notify(saved.is_new ? "分类标准已创建并启用" : "分类标准已更新并启用");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const startSampleValidation = async (
    reviewFile,
    comparisonType = "standard_version",
  ) => {
    setBusy("validation");
    try {
      const saved = await persistDraft();
      if (!reviewFile && !validationSourceId) throw new Error("当前没有可用的样本来源");
      const value = reviewFile
        ? await classificationStandardApi.createReviewStandardValidationRun(
            saved.id,
            reviewFile,
            saved.revision,
            validationSampleSize,
            comparisonType,
          )
        : await classificationStandardApi.createClassificationStandardValidationRun(
            saved.id,
            {
              expected_revision: saved.revision,
              source_result_version_id: validationSourceId,
              sample_size: validationSampleSize,
              comparison_type: comparisonType,
            },
          );
      await loadValidation(saved.id, value.id);
      notify("样本验证已进入队列");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const approveSampleValidation = async (runId, note) => {
    if (!draft) return;
    setBusy("approval");
    try {
      const value =
        await classificationStandardApi.approveClassificationStandardValidationRun(
          runId,
          {
            expected_revision: draft.revision,
            note,
          },
        );
      await loadValidation(draft.id, value.id);
      notify("当前草稿修订已人工确认，可进入发布确认");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const importJson = async (event) => {
    const file = event.target.files?.[0];
    if (!file || !detail) return;
    setBusy("import");
    try {
      const document = JSON.parse(await file.text());
      const workingDraft =
        draft ??
        (await classificationStandardApi.createClassificationStandardDraft(detail.id));
      const imported =
        await classificationStandardApi.importClassificationStandardDraft(
          workingDraft.id,
          {
            expected_revision: workingDraft.revision,
            document,
            change_reason: `导入 ${file.name}`,
          },
        );
      setDraft(imported);
      setContent(clone(imported.content));
      setChangeReason(imported.change_reason || `导入 ${file.name}`);
      await loadStandards();
      await loadValidation(imported.id);
      notify("JSON 已导入草稿，请检查后再发布");
    } catch (error) {
      notify(
        error instanceof SyntaxError ? "JSON 文件格式错误" : error.message,
        "error",
      );
    } finally {
      event.target.value = "";
      setBusy("");
    }
  };

  const deleteStandard = async () => {
    if (!deleteTarget) return;
    setBusy("delete");
    try {
      const result = await classificationStandardApi.deleteClassificationStandard(
        deleteTarget.id,
      );
      await loadStandards();
      setDeleteTarget(null);
      navigateHash("classification-standards");
      notify(result.mode === "deleted" ? "分类标准已删除" : "分类标准已停用");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const restoreVersion = async () => {
    if (!restoreTarget || !detail) return;
    setBusy("restore");
    try {
      await classificationStandardApi.restoreClassificationStandardVersion(
        restoreTarget.id,
      );
      setRestoreTarget(null);
      await loadStandards();
      await loadSelected(detail.id);
      navigateHash("classification-standards", {
        standard: detail.id,
        view: "edit",
      });
      notify(`已从 V${restoreTarget.version_no} 创建恢复草稿，请检查后再发布`);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  if (loading) return <div className="inline-loading">正在读取分类标准…</div>;

  return (
    <div className="standard-page classification-standard-page">
      {mode === "list" && (
        <StandardList
          standards={filteredStandards}
          totals={totals}
          query={query}
          statusFilter={statusFilter}
          onQueryChange={setQuery}
          onStatusChange={setStatusFilter}
          onCreate={() => navigateHash("classification-standards", { view: "new" })}
          onView={(standard) =>
            navigateHash("classification-standards", { standard: standard.id })
          }
          onDelete={setDeleteTarget}
        />
      )}

      {(mode === "new" || mode === "edit") &&
        (pageLoading ? (
          <div className="inline-loading">正在读取分类标准…</div>
        ) : (
          <StandardWorkspace
            key={`${selectedId || "new"}-${detail?.standard_version_id || ""}`}
            initiallyEditing={route.query.view === "edit" || mode === "new"}
            versions={versions}
            notify={notify}
            onDelete={() => setDeleteTarget(detail)}
            onRestore={setRestoreTarget}
            savedContent={savedContent}
            focusLabelCode={route.query.label}
            isNew={mode === "new"}
            detail={detail}
            draft={draft}
            content={content}
            changeReason={changeReason}
            busy={busy}
            dirty={dirty}
            validationSources={validationSources}
            validationRuns={validationRuns}
            selectedValidation={selectedValidation}
            validationSourceId={validationSourceId}
            validationSampleSize={validationSampleSize}
            onContentChange={setContent}
            onReasonChange={setChangeReason}
            onSave={saveDraft}
            onPublish={publish}
            onBack={() => navigateHash("classification-standards")}
            onValidationSourceChange={setValidationSourceId}
            onValidationSampleSizeChange={setValidationSampleSize}
            onValidationRun={startSampleValidation}
            onValidationApprove={approveSampleValidation}
            onImport={importJson}
            onValidationSelect={async (runId) => {
              try {
                setSelectedValidation(
                  await classificationStandardApi.classificationStandardValidationRun(
                    runId,
                  ),
                );
              } catch (error) {
                notify(error.message, "error");
              }
            }}
          />
        ))}

      {deleteTarget && (
        <Modal
          className="standard-lifecycle-modal"
          eyebrow={
            deleteTarget.delete_mode === "delete" ? "删除分类标准" : "停用分类标准"
          }
          title={
            deleteTarget.delete_mode === "delete"
              ? `永久删除“${deleteTarget.name}”`
              : `停用“${deleteTarget.name}”`
          }
          description={
            deleteTarget.delete_mode === "delete"
              ? "该标准从未发布且未被任务使用，删除后无法恢复。"
              : "该标准已发布或已被任务使用。停用后新任务不再使用它，历史任务与结果保持不变。"
          }
          onClose={() => busy !== "delete" && setDeleteTarget(null)}
        >
          {deleteTarget.delete_mode !== "delete" && deleteTarget.draft_id && (
            <p className="standard-deactivate-warning">
              此标准还有未发布草稿。停用时，草稿及其样本验证记录将一并删除，无法恢复。
            </p>
          )}
          <div className="standard-delete-actions">
            <button
              type="button"
              className="secondary-button"
              disabled={busy === "delete"}
              onClick={() => setDeleteTarget(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="danger-button"
              disabled={busy === "delete"}
              onClick={deleteStandard}
            >
              {busy === "delete"
                ? "处理中"
                : deleteTarget.delete_mode === "delete"
                  ? "确认删除"
                  : "确认停用"}
            </button>
          </div>
        </Modal>
      )}

      {restoreTarget && (
        <Modal
          eyebrow="恢复历史版本"
          title={`恢复 V${restoreTarget.version_no} 为新草稿`}
          description="不会覆盖任何历史版本，也不会立即改变当前启用版本。请在草稿中检查后再发布。"
          onClose={() => setRestoreTarget(null)}
        >
          <div className="standard-delete-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() => setRestoreTarget(null)}
            >
              取消
            </button>
            <button
              type="button"
              className="primary-button"
              disabled={busy === "restore"}
              onClick={restoreVersion}
            >
              {busy === "restore" ? "创建中" : "创建恢复草稿"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function StandardList({
  standards,
  totals,
  query,
  statusFilter,
  onQueryChange,
  onStatusChange,
  onCreate,
  onView,
  onDelete,
}) {
  return (
    <>
      <PageHeading
        eyebrow="语义分类治理"
        title="分类标准"
        description="维护商品品类与退货问题标签，分析任务会自动读取当前启用版本。"
        action={
          <button type="button" className="primary-button" onClick={onCreate}>
            <Plus size={16} /> 新建分类标准
          </button>
        }
      />
      <section className="standard-library-summary" aria-label="分类标准汇总">
        <div>
          <BookOpenText size={20} />
          <span>使用中标准</span>
          <strong>{totals.active}</strong>
        </div>
        <div>
          <CheckCircle size={20} />
          <span>覆盖品类</span>
          <strong>{totals.categories}</strong>
        </div>
        <div>
          <Tag size={20} />
          <span>分类标签</span>
          <strong>{totals.labels}</strong>
        </div>
      </section>
      <section className="standard-library-card">
        <div className="standard-library-toolbar">
          <label className="standard-search-box">
            <MagnifyingGlass size={17} />
            <input
              aria-label="搜索分类标准"
              placeholder="搜索标准名称或适用商品"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </label>
          <div className="standard-status-filter" role="group" aria-label="标准状态">
            {[
              ["all", "全部状态"],
              ["active", "使用中"],
              ["inactive", "未使用"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={statusFilter === value ? "active" : ""}
                aria-pressed={statusFilter === value}
                onClick={() => onStatusChange(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {standards.length === 0 ? (
          <EmptyState
            icon={BookOpenText}
            title="没有符合条件的分类标准"
            description="调整搜索条件，或新建一套分类标准。"
          />
        ) : (
          <div className="standard-table-wrap">
            <table className="standard-library-table">
              <thead>
                <tr>
                  <th>分类标准</th>
                  <th>适用品类</th>
                  <th>标签体系</th>
                  <th>当前状态</th>
                  <th>最近更新</th>
                  <th aria-label="操作" />
                </tr>
              </thead>
              <tbody>
                {standards.map((standard) => (
                  <tr key={standard.id}>
                    <td>
                      <button
                        type="button"
                        className="standard-name-button"
                        onClick={() => onView(standard)}
                      >
                        <b>{standard.name}</b>
                        <span>{standard.product_context}</span>
                      </button>
                    </td>
                    <td>
                      <b>{standard.category_count}</b> 个品类
                    </td>
                    <td>
                      <b>{standard.label_count}</b> 个标签 ·{" "}
                      {standard.label_group_count} 组
                    </td>
                    <td>
                      <span className={`standard-status ${standard.status}`}>
                        {statusLabel(standard)}
                      </span>
                      <small>
                        {Number(standard.version_no) > 0
                          ? `V${standard.version_no}`
                          : "草稿"}
                        {standard.draft_id && Number(standard.version_no) > 0
                          ? " · 有草稿"
                          : ""}
                      </small>
                    </td>
                    <td>{formatDate(standard.updated_at)}</td>
                    <td>
                      <div className="standard-row-actions">
                        <button type="button" onClick={() => onView(standard)}>
                          查看
                        </button>
                        {(standard.status === "active" ||
                          standard.delete_mode === "delete") && (
                          <button
                            type="button"
                            className="standard-deactivate-action"
                            aria-label={`${standard.delete_mode === "delete" ? "删除标准" : "停用标准"}：${standard.name}`}
                            onClick={() => onDelete(standard)}
                          >
                            {standard.delete_mode === "delete" ? "删除" : "停用"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function StandardVersionHistory({ standard, versions, onRestore }) {
  return (
    <details className="standard-version-history">
      <summary>
        <ClockCounterClockwise size={17} /> 版本记录（{versions.length}）
      </summary>
      <div>
        {versions.map((version) => (
          <div key={version.id}>
            <b>V{version.version_no}</b>
            <span>{version.version_reason}</span>
            <small>{formatDate(version.published_at)}</small>
            <a
              href={classificationStandardApi.classificationStandardVersionExportUrl(
                version.id,
              )}
              aria-label={`导出 V${version.version_no} JSON`}
            >
              <DownloadSimple size={14} /> 导出JSON
            </a>
            {version.id === standard.standard_version_id ? (
              <span className="standard-version-current">当前版本</span>
            ) : (
              <button
                type="button"
                className="standard-version-restore"
                disabled={Boolean(standard.draft_id)}
                title={standard.draft_id ? "请先处理现有草稿" : undefined}
                aria-label={`恢复 V${version.version_no} 为草稿`}
                onClick={() => onRestore(version)}
              >
                <ClockCounterClockwise size={14} /> 恢复为草稿
              </button>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}

function StandardWorkspace({
  initiallyEditing,
  versions,
  notify,
  onDelete,
  onRestore,
  savedContent,
  focusLabelCode,
  isNew,
  detail,
  draft,
  content,
  changeReason,
  busy,
  dirty,
  validationSources,
  validationRuns,
  selectedValidation,
  validationSourceId,
  validationSampleSize,
  onContentChange,
  onReasonChange,
  onSave,
  onPublish,
  onBack,
  onValidationSourceChange,
  onValidationSampleSizeChange,
  onValidationRun,
  onValidationApprove,
  onImport,
  onValidationSelect,
}) {
  const [section, setSection] = useState(isNew ? "settings" : "labels");
  const [confirmBack, setConfirmBack] = useState(false);
  const editable = isNew || detail?.status === "active" || Boolean(draft);
  const baseContent = draft?.base_snapshot
    ? contentFromSnapshot(draft.base_snapshot)
    : detail?.snapshot
      ? contentFromSnapshot(detail.snapshot)
      : null;
  const changes = labelChanges(content.labels, baseContent?.labels).filter(
    (entry) => entry.status !== "未修改",
  );
  const settingsChanges = Object.keys(content).filter(
    (key) =>
      key !== "labels" &&
      JSON.stringify(content[key]) !== JSON.stringify(baseContent?.[key]),
  ).length;
  const changeCount = changes.length + settingsChanges;
  const publicationReady = validationRuns.some((run) => run.publication_ready);
  const awaitingApproval = validationRuns.some(
    (run) =>
      run.is_current &&
      run.status === "completed" &&
      (run.source?.comparison_type ?? "standard_version") === "standard_version" &&
      Number(run.error_count) === 0 &&
      !run.approved_at,
  );
  const publishDisabled = Boolean(busy) || !draft || dirty || !publicationReady;
  const publishLabel = !draft
    ? "请先保存草稿"
    : dirty
      ? "请先保存修改"
      : publicationReady
        ? "发布并启用"
        : awaitingApproval
          ? "等待人工确认"
          : "等待样本验证";

  return (
    <>
      <div className="standard-subpage-heading editor-heading">
        <button
          type="button"
          className="icon-button"
          aria-label="返回"
          onClick={() => (dirty ? setConfirmBack(true) : onBack())}
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1>{isNew ? "建立品类与标签体系" : detail?.name}</h1>
          <span>
            {draft
              ? `未发布草稿 r${draft.revision} · 当前启用版本 V${draft.base_version_no}`
              : detail
                ? `${detail.status === "active" ? "当前启用版本" : "已停用版本"} V${detail.version_no}`
                : "新建标准"}
          </span>
        </div>
        {detail && (detail.status === "active" || detail.delete_mode === "delete") && (
          <details className="standard-more-menu">
            <summary>更多</summary>
            <button type="button" disabled={Boolean(busy)} onClick={onDelete}>
              {detail.delete_mode === "delete" ? "删除标准" : "停用标准"}
            </button>
          </details>
        )}
      </div>

      <nav className="standard-editor-tabs" aria-label="标准管理分区">
        {[
          ["labels", "标签管理"],
          ["settings", "标准设置"],
        ].map(([value, title]) => (
          <button
            key={value}
            type="button"
            aria-current={section === value ? "page" : undefined}
            onClick={() => setSection(value)}
          >
            {title}
          </button>
        ))}
      </nav>

      <ClassificationStandardEditor
        section={section}
        initiallyEditing={initiallyEditing}
        editable={editable}
        notify={notify}
        busy={Boolean(busy)}
        savedContent={savedContent}
        focusLabelCode={focusLabelCode}
        content={content}
        baseContent={baseContent}
        onChange={onContentChange}
      />

      <div className="standard-settings-extra" hidden={section !== "settings"}>
        <section className="standard-detail-section">
          <h2>识别策略</h2>
          <label>
            当前草稿使用
            <select
              aria-label="识别策略"
              disabled={!editable}
              value={content.recognition_profile ?? "legacy_v3"}
              onChange={(event) =>
                onContentChange({ ...content, recognition_profile: event.target.value })
              }
            >
              <option value="legacy_v3">现有策略 · 定义与关键词</option>
              <option value="semantic_v1">语义策略 · 定义、边界与证据</option>
            </select>
          </label>
          <p>保存只修改草稿；通过发布验证并启用后，新任务才使用该策略。</p>
        </section>
        {!isNew && editable && (
          <section className="standard-json-transfer">
            <div>
              <b>JSON 数据交换</b>
              <span>导入只替换当前草稿的业务内容，不会直接发布。</span>
            </div>
            <label
              className={`secondary-button standard-json-import-button ${
                busy ? "disabled" : ""
              }`}
            >
              <UploadSimple size={15} />
              {busy === "import" ? "导入中" : "导入JSON"}
              <input
                type="file"
                accept="application/json,.json"
                aria-label="选择分类标准 JSON 文件"
                disabled={Boolean(busy)}
                onChange={onImport}
              />
            </label>
          </section>
        )}

        {detail && (
          <StandardVersionHistory
            standard={{ ...detail, draft_id: draft?.id }}
            versions={versions}
            onRestore={onRestore}
          />
        )}
      </div>

      <div className="standard-review-panel" hidden={section !== "review"}>
        <section className="standard-editor-section standard-change-preview">
          <header>
            <h2>发布前检查</h2>
            <span>对比当前启用版本</span>
          </header>
          <p>保存草稿不会影响运行中的标准。检查变更后，完成样本验证再发布。</p>
          {content.recognition_profile !== baseContent?.recognition_profile && (
            <p>
              识别策略：
              {baseContent?.recognition_profile === "semantic_v1"
                ? "语义策略"
                : "现有策略"}
              {" → "}
              {content.recognition_profile === "semantic_v1"
                ? "语义策略（定义、边界与证据）"
                : "现有策略（定义与关键词）"}
            </p>
          )}
          {changes.length ? (
            changes.map(({ label, before, status }) => (
              <article key={label.code}>
                <header>
                  <strong>{label.name || "未命名标签"}</strong>
                  <span className="label-change-badge changed">{status}</span>
                </header>
                <code>{label.code}</code>
                <p>{label.description}</p>
                {status === "已修改" && (
                  <div>
                    <span>原搜索别名：{before.keywords?.join("、") || "无"}</span>
                    <span>新搜索别名：{label.keywords?.join("、") || "无"}</span>
                  </div>
                )}
                {[
                  ["原", before],
                  ["新", status === "拟停用" ? null : label],
                ].map(
                  ([title, value]) =>
                    value &&
                    Boolean(
                      before?.exclusions?.length ||
                      before?.examples?.length ||
                      label.exclusions?.length ||
                      label.examples?.length,
                    ) && (
                      <div key={title}>
                        <span>
                          {title}排除说明：{value.exclusions?.join("；") || "无"}
                        </span>
                        <span>
                          {title}判定示例：{value.examples?.length ? "" : "无"}
                        </span>
                        {value.examples?.map((example, index) => (
                          <p key={index}>
                            {example.applies ? "适用" : "不适用"}
                            {example.sentiment ? ` · ${example.sentiment}` : ""}：
                            {example.text} — {example.explanation}
                          </p>
                        ))}
                      </div>
                    ),
                )}
              </article>
            ))
          ) : (
            <p>标签没有变化。基本信息与分类设置的修改会随草稿一起保存。</p>
          )}
          {JSON.stringify(content.validation_rules) !==
            JSON.stringify(baseContent?.validation_rules ?? {}) && (
            <p className="label-unsaved-hint">
              标签校验规则有变化，请检查相关语义边界、分类指令与 Listing 承诺配置。
            </p>
          )}
          {!dirty && draft?.validation.blocking?.length > 0 && (
            <div className="label-unsaved-hint" role="status">
              {draft.validation.blocking.join("；")}
            </div>
          )}
        </section>
        <section className="standard-change-reason">
          <label>
            变更说明
            <input
              value={changeReason}
              onChange={(event) => onReasonChange(event.target.value)}
            />
          </label>
          <span>用于版本记录，不影响智能体判断。</span>
        </section>

        <details className="standard-optional-validation" open>
          <summary>发布前样本验证（必需）</summary>
          {draft ? (
            <ClassificationStandardValidation
              draft={draft}
              sources={validationSources}
              runs={validationRuns}
              selectedRun={selectedValidation}
              sourceId={validationSourceId}
              sampleSize={validationSampleSize}
              busy={busy === "validation"}
              approvalBusy={busy === "approval"}
              dirty={dirty}
              onSourceChange={onValidationSourceChange}
              onSampleSizeChange={onValidationSampleSizeChange}
              onRun={onValidationRun}
              onApprove={onValidationApprove}
              onSelectRun={onValidationSelect}
            />
          ) : (
            <p>请先保存草稿，再运行样本验证；验证通过后才能启用新版本。</p>
          )}
        </details>
      </div>
      {editable && (
        <footer className="standard-editor-footer">
          <div role="status">
            <strong>
              {changeCount
                ? `有 ${changeCount} 项变更${dirty ? " · 未保存" : " · 已保存"}`
                : "暂无变更"}
            </strong>
            {draft && !dirty && <span>草稿 r{draft.revision}，尚未发布</span>}
          </div>
          <div>
            <button
              type="button"
              className="secondary-button"
              disabled={Boolean(busy)}
              onClick={onSave}
            >
              {busy === "save" ? "保存中" : "保存草稿"}
            </button>
            {section === "review" ? (
              <button
                type="button"
                className="primary-button"
                disabled={publishDisabled}
                title={publishDisabled ? publishLabel : undefined}
                onClick={onPublish}
              >
                {busy === "publish" ? "启用中" : publishLabel}
              </button>
            ) : (
              <button
                type="button"
                className="primary-button"
                disabled={Boolean(busy) || (!dirty && !draft)}
                onClick={() => setSection("review")}
              >
                发布
              </button>
            )}
          </div>
        </footer>
      )}
      {confirmBack && (
        <Modal
          eyebrow="未保存修改"
          title="离开编辑页？"
          onClose={() => setConfirmBack(false)}
        >
          <div className="label-action-confirm">
            <p>尚未保存的修改会丢失。可以继续编辑并保存草稿，或放弃本次未保存内容。</p>
            <div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setConfirmBack(false)}
              >
                继续编辑
              </button>
              <button type="button" className="danger-button" onClick={onBack}>
                放弃修改并返回
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
