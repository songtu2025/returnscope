import { useCallback, useEffect, useMemo, useState } from "react";
import "../../styles/classification-standards.css";

import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  ClassificationStandardDeleteDialog,
  ClassificationStandardRestoreDialog,
} from "./ClassificationStandardDialogs";
import { ClassificationStandardList } from "./ClassificationStandardList";
import { ClassificationStandardWorkspace } from "./ClassificationStandardWorkspace";
import {
  classificationStandardContentFieldErrors,
  clearClassificationStandardContentFieldError,
  cloneClassificationStandardContent,
  contentFromClassificationStandardSnapshot,
  EMPTY_CLASSIFICATION_STANDARD_CONTENT,
  validateClassificationStandardContent,
} from "./classificationStandardContent";

export function ClassificationStandardsPage({ route, notify }) {
  const [standards, setStandards] = useState([]);
  const [detail, setDetail] = useState(null);
  const [versions, setVersions] = useState([]);
  const [draft, setDraft] = useState(null);
  const [content, setContent] = useState(
    cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT),
  );
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
  const [fieldErrors, setFieldErrors] = useState({});
  const [validationAttempt, setValidationAttempt] = useState(0);

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
          cloneClassificationStandardContent(
            draftValue?.content ??
              contentFromClassificationStandardSnapshot(standard.snapshot),
          ),
        );
        setFieldErrors({});
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
      setContent(
        cloneClassificationStandardContent(EMPTY_CLASSIFICATION_STANDARD_CONTENT),
      );
      setFieldErrors({});
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
    (detail?.snapshot
      ? contentFromClassificationStandardSnapshot(detail.snapshot)
      : EMPTY_CLASSIFICATION_STANDARD_CONTENT);
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
    const error = validateClassificationStandardContent(content);
    if (error) {
      setFieldErrors(classificationStandardContentFieldErrors(content));
      setValidationAttempt((value) => value + 1);
      throw new Error(error);
    }
    setFieldErrors({});

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
    setContent(cloneClassificationStandardContent(workingDraft.content));
    return workingDraft;
  };

  const saveDraft = async () => {
    setBusy("save");
    try {
      const saved = await persistDraft();
      const checked =
        await classificationStandardApi.validateClassificationStandardDraft(
          saved.id,
          saved.revision,
        );
      setDraft(checked);
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

  const prepareExcelDraft = async () => {
    if (dirty && (draft || content.labels.length))
      throw new Error("请先保存当前修改，再导入标签框架");
    if (draft) return draft;
    let created;
    if (mode === "new") {
      const category = content.variants[0];
      if (
        !content.name.trim() ||
        !content.product_context.trim() ||
        !category?.category_a.trim() ||
        !category?.category_b.trim()
      )
        throw new Error("请先填写标准名称、适用商品说明和适用品类");
      created = await classificationStandardApi.createClassificationStandard({
        name: content.name.trim(),
        product_context: content.product_context.trim(),
        category_a: category.category_a.trim(),
        category_b: category.category_b.trim(),
      });
    } else {
      created = await classificationStandardApi.createClassificationStandardDraft(
        detail.id,
      );
    }
    setDraft(created);
    setContent(cloneClassificationStandardContent(created.content));
    setChangeReason("导入层级标签框架");
    return created;
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
      setContent(cloneClassificationStandardContent(imported.content));
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
    <AntdProvider>
      <div className="standard-page classification-standard-page">
        {mode === "list" && (
          <ClassificationStandardList
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
            <ClassificationStandardWorkspace
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
              fieldErrors={fieldErrors}
              validationAttempt={validationAttempt}
              onContentChange={(value, field) => {
                setContent(value);
                setFieldErrors((current) =>
                  clearClassificationStandardContentFieldError(current, field),
                );
              }}
              onReasonChange={setChangeReason}
              onSave={saveDraft}
              onPublish={publish}
              onBack={() => navigateHash("classification-standards")}
              onValidationSourceChange={setValidationSourceId}
              onValidationSampleSizeChange={setValidationSampleSize}
              onValidationRun={startSampleValidation}
              onValidationApprove={approveSampleValidation}
              onImport={importJson}
              onPrepareExcel={prepareExcelDraft}
              onApplyExcel={(value, filename) => {
                setContent(value);
                setChangeReason(`导入 ${filename}`);
                setFieldErrors({});
                notify("已采用层级预览，请检查层级和评价方向，保存后可运行样本验证");
              }}
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

        <ClassificationStandardDeleteDialog
          target={deleteTarget}
          busy={busy}
          onClose={() => setDeleteTarget(null)}
          onConfirm={deleteStandard}
        />

        <ClassificationStandardRestoreDialog
          target={restoreTarget}
          busy={busy}
          onClose={() => setRestoreTarget(null)}
          onConfirm={restoreVersion}
        />
      </div>
    </AntdProvider>
  );
}
