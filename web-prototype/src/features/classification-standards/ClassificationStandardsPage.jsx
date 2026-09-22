import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, WarningCircle } from "@phosphor-icons/react";
import "../../styles/classification-standards.css";

import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { EmptyState, PageLoadingState } from "../../components/SharedUi";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  ClassificationStandardDeleteDialog,
  ClassificationStandardRestoreDialog,
} from "./ClassificationStandardDialogs";
import { ClassificationStandardList } from "./ClassificationStandardList";
import { ClassificationStandardWorkspace } from "./ClassificationStandardWorkspace";
import { useClassificationStandardDraftController } from "./useClassificationStandardDraftController";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSummary} ClassificationStandardSummary */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {{query: Record<string, string | undefined>}} ClassificationStandardsRoute */
/** @typedef {{route: ClassificationStandardsRoute, notify: (message: string, tone?: string) => void}} ClassificationStandardsPageProps */

/** @param {unknown} error */
function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/** @param {ClassificationStandardsPageProps} props */
export function ClassificationStandardsPage({ route, notify }) {
  const [standards, setStandards] = useState(
    /** @type {ClassificationStandardSummary[]} */ ([]),
  );
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(
    /** @type {"all" | "active" | "inactive"} */ ("all"),
  );
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(
    /** @type {ClassificationStandardSummary | null} */ (null),
  );
  const [restoreTarget, setRestoreTarget] = useState(
    /** @type {ClassificationStandardVersion | null} */ (null),
  );

  const selectedId = route.query.standard || "";
  const mode = route.query.view === "new" ? "new" : selectedId ? "edit" : "list";

  const loadStandards = useCallback(async () => {
    const values = await classificationStandardApi.classificationStandards();
    setStandards(values);
    return values;
  }, []);

  useEffect(() => {
    loadStandards()
      .catch((error) => notify(errorMessage(error), "error"))
      .finally(() => setLoading(false));
  }, [loadStandards, notify]);

  const {
    detail,
    versions,
    draft,
    content,
    savedContent,
    changeReason,
    pageLoading,
    pageError,
    dirty,
    fieldErrors,
    validationAttempt,
    validationSources,
    validationRuns,
    selectedValidation,
    validationSourceId,
    validationSampleSize,
    setValidationSourceId,
    setValidationSampleSize,
    startSampleValidation,
    selectValidation,
    setChangeReason,
    loadSelected,
    saveDraft,
    prepareExcelDraft,
    publish,
    importJson,
    changeContent,
    applyExcel,
  } = useClassificationStandardDraftController({
    mode,
    selectedId,
    notify,
    loadStandards,
    setBusy,
  });

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
      notify(errorMessage(error), "error");
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
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  if (loading) {
    return (
      <div className="standard-page classification-standard-page">
        {mode === "edit" && (
          <button
            type="button"
            className="icon-button"
            aria-label="返回"
            onClick={() => navigateHash("classification-standards")}
          >
            <ArrowLeft size={18} />
          </button>
        )}
        <PageLoadingState label="正在读取分类标准…" />
      </div>
    );
  }

  const detailError = pageError?.id === selectedId ? pageError.message : "";
  const detailPending =
    mode === "edit" && (pageLoading || (!detailError && detail?.id !== selectedId));

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
            onView={(/** @type {ClassificationStandardSummary} */ standard) =>
              navigateHash("classification-standards", { standard: standard.id })
            }
            onDelete={setDeleteTarget}
          />
        )}

        {(mode === "new" || mode === "edit") &&
          (detailPending ? (
            <>
              <button
                type="button"
                className="icon-button"
                aria-label="返回"
                onClick={() => navigateHash("classification-standards")}
              >
                <ArrowLeft size={18} />
              </button>
              <PageLoadingState label="正在读取分类标准…" />
            </>
          ) : detailError && mode === "edit" ? (
            <>
              <button
                type="button"
                className="icon-button"
                aria-label="返回"
                onClick={() => navigateHash("classification-standards")}
              >
                <ArrowLeft size={18} />
              </button>
              <EmptyState
                icon={WarningCircle}
                title="分类标准读取失败"
                description={detailError}
                action={
                  <button
                    className="secondary-button"
                    onClick={() =>
                      loadSelected(selectedId).catch((error) =>
                        notify(errorMessage(error), "error"),
                      )
                    }
                  >
                    重新加载
                  </button>
                }
              />
            </>
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
              onContentChange={changeContent}
              onReasonChange={setChangeReason}
              onSave={saveDraft}
              onPublish={publish}
              onBack={() => navigateHash("classification-standards")}
              onValidationSourceChange={setValidationSourceId}
              onValidationSampleSizeChange={setValidationSampleSize}
              onValidationRun={startSampleValidation}
              onImport={importJson}
              onPrepareExcel={prepareExcelDraft}
              onApplyExcel={applyExcel}
              onValidationSelect={selectValidation}
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
