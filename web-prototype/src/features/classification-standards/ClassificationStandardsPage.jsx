import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpenText,
  CheckCircle,
  ClockCounterClockwise,
  DownloadSimple,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Tag,
  Trash,
  UploadSimple,
  WarningCircle,
} from "@phosphor-icons/react";
import { navigateHash } from "../../app/hashRouter";
import { EmptyState, Modal, PageHeading } from "../../components/SharedUi";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import { ClassificationStandardEditor } from "./ClassificationStandardDraftEditor";
import { ClassificationStandardValidation } from "./ClassificationStandardValidation";

const clone = (value) => JSON.parse(JSON.stringify(value));

const EMPTY_CONTENT = {
  name: "",
  product_context: "",
  instructions: ["依据标签业务定义判断退货原因"],
  allowed_parts: ["UNSPECIFIED"],
  variants: [{ category_a: "", category_b: "", attributes: {} }],
  labels: [],
};

function contentFromSnapshot(snapshot) {
  return {
    name: snapshot.name,
    product_context: snapshot.taxonomy.product_context,
    instructions: snapshot.taxonomy.instructions ?? [],
    allowed_parts: snapshot.taxonomy.allowed_parts ?? ["UNSPECIFIED"],
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
  const mode =
    route.query.view === "new"
      ? "new"
      : selectedId
        ? route.query.view === "edit"
          ? "edit"
          : "detail"
        : "list";

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

  const dirty = Boolean(
    draft && JSON.stringify(content) !== JSON.stringify(draft.content),
  );

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
      navigateHash("classification-standards", { standard: standard.id });
      notify(saved.is_new ? "分类标准已创建并启用" : "分类标准已更新并启用");
    } catch (error) {
      notify(error.message, "error");
    } finally {
      setBusy("");
    }
  };

  const startSampleValidation = async () => {
    setBusy("validation");
    try {
      const saved = await persistDraft();
      if (!validationSourceId) throw new Error("当前没有可用的样本来源");
      const value =
        await classificationStandardApi.createClassificationStandardValidationRun(
          saved.id,
          {
            expected_revision: saved.revision,
            source_result_version_id: validationSourceId,
            sample_size: validationSampleSize,
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
          onEdit={(standard) =>
            navigateHash("classification-standards", {
              standard: standard.id,
              view: "edit",
            })
          }
          onDelete={setDeleteTarget}
        />
      )}

      {mode === "detail" &&
        (pageLoading || !detail ? (
          <div className="inline-loading">正在读取分类标准…</div>
        ) : (
          <StandardDetail
            standard={detail}
            versions={versions}
            onBack={() => navigateHash("classification-standards")}
            onEdit={() =>
              navigateHash("classification-standards", {
                standard: detail.id,
                view: "edit",
              })
            }
            onDelete={() => setDeleteTarget(detail)}
            onRestore={setRestoreTarget}
          />
        ))}

      {(mode === "new" || mode === "edit") &&
        (pageLoading ? (
          <div className="inline-loading">正在读取分类标准…</div>
        ) : (
          <StandardEditPage
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
            onBack={() =>
              navigateHash(
                "classification-standards",
                detail ? { standard: detail.id } : {},
              )
            }
            onValidationSourceChange={setValidationSourceId}
            onValidationSampleSizeChange={setValidationSampleSize}
            onValidationRun={startSampleValidation}
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
          eyebrow="删除分类标准"
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
          onClose={() => setDeleteTarget(null)}
        >
          <div className="standard-delete-actions">
            <button
              type="button"
              className="secondary-button"
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
  onEdit,
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
                      </small>
                    </td>
                    <td>{formatDate(standard.updated_at)}</td>
                    <td>
                      <div className="standard-row-actions">
                        <button type="button" onClick={() => onView(standard)}>
                          查看
                        </button>
                        {(standard.status === "active" || standard.draft_id) && (
                          <button type="button" onClick={() => onEdit(standard)}>
                            编辑
                          </button>
                        )}
                        <button
                          type="button"
                          className="danger-text"
                          onClick={() => onDelete(standard)}
                        >
                          删除
                        </button>
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

function StandardDetail({ standard, versions, onBack, onEdit, onDelete, onRestore }) {
  const snapshot = standard.snapshot;
  const groups = Object.groupBy
    ? Object.groupBy(snapshot.taxonomy.labels, (label) => label.group)
    : snapshot.taxonomy.labels.reduce((result, label) => {
        result[label.group] = [...(result[label.group] ?? []), label];
        return result;
      }, {});
  const editable = standard.status === "active" || standard.draft_id;

  return (
    <>
      <div className="standard-subpage-heading">
        <button
          type="button"
          className="icon-button"
          aria-label="返回列表"
          onClick={onBack}
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <p className="eyebrow">分类标准</p>
          <h1>{standard.name}</h1>
          <span>{standard.product_context}</span>
        </div>
        <div className="standard-heading-actions">
          {editable && (
            <button type="button" className="primary-button" onClick={onEdit}>
              <PencilSimple size={16} /> 编辑
            </button>
          )}
          <button type="button" className="danger-button" onClick={onDelete}>
            <Trash size={16} /> 删除
          </button>
        </div>
      </div>

      <section className="standard-runtime-note">
        {standard.status === "active" ? (
          <CheckCircle size={20} />
        ) : (
          <WarningCircle size={20} />
        )}
        <div>
          <b>
            {standard.status === "active"
              ? `当前启用版本 V${standard.version_no}`
              : "该标准已停止用于新任务"}
          </b>
          <span>
            新建分析任务会读取当前启用版本并固定到任务中；历史任务始终保留原版本。
          </span>
        </div>
      </section>

      <section className="standard-detail-section">
        <header>
          <h2>适用品类</h2>
          <span>{snapshot.variants.length} 个</span>
        </header>
        <div className="standard-category-grid">
          {snapshot.variants.map((variant, index) => (
            <div key={`${variant.category_a}-${variant.category_b}-${index}`}>
              <span>{variant.category_a}</span>
              <b>{variant.category_b}</b>
            </div>
          ))}
        </div>
      </section>

      <section className="standard-detail-section">
        <header>
          <h2>分类标签体系</h2>
          <span>{snapshot.taxonomy.labels.length} 个标签</span>
        </header>
        <div className="standard-label-groups">
          {Object.entries(groups).map(([group, labels]) => (
            <article key={group}>
              <header>
                <h3>{group}</h3>
                <span>{labels.length}</span>
              </header>
              {labels.map((label) => (
                <div key={label.code}>
                  <span>
                    <b>{label.name}</b>
                    <code>{label.code}</code>
                  </span>
                  <p>{label.description}</p>
                  {label.keywords?.length > 0 && (
                    <p>关键词：{label.keywords.join("、")}</p>
                  )}
                </div>
              ))}
            </article>
          ))}
        </div>
      </section>

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
    </>
  );
}

function StandardEditPage({
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
  onImport,
  onValidationSelect,
}) {
  return (
    <>
      <div className="standard-subpage-heading editor-heading">
        <button
          type="button"
          className="icon-button"
          aria-label="返回"
          onClick={onBack}
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <p className="eyebrow">{isNew ? "新建分类标准" : "编辑分类标准"}</p>
          <h1>{isNew ? "建立品类与标签体系" : detail?.name}</h1>
          <span>保存启用后，新建分析任务将自动读取新版本。</span>
        </div>
        <div className="standard-heading-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={Boolean(busy)}
            onClick={onSave}
          >
            {busy === "save" ? "保存中" : "保存草稿"}
          </button>
          <button
            type="button"
            className="primary-button"
            disabled={Boolean(busy)}
            onClick={onPublish}
          >
            {busy === "publish" ? "启用中" : "保存并启用"}
          </button>
        </div>
      </div>

      <ClassificationStandardEditor
        content={content}
        baseContent={
          draft?.base_snapshot
            ? contentFromSnapshot(draft.base_snapshot)
            : detail?.snapshot
              ? contentFromSnapshot(detail.snapshot)
              : null
        }
        onChange={onContentChange}
      />

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

      {!isNew && (
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

      <details className="standard-optional-validation">
        <summary>小样本验证（可选）</summary>
        {draft ? (
          <ClassificationStandardValidation
            draft={draft}
            sources={validationSources}
            runs={validationRuns}
            selectedRun={selectedValidation}
            sourceId={validationSourceId}
            sampleSize={validationSampleSize}
            busy={busy === "validation"}
            dirty={dirty}
            onSourceChange={onValidationSourceChange}
            onSampleSizeChange={onValidationSampleSizeChange}
            onRun={onValidationRun}
            onSelectRun={onValidationSelect}
          />
        ) : (
          <p>如需验证标签效果，请先保存草稿。该步骤不影响正常保存启用。</p>
        )}
      </details>
    </>
  );
}
