import { useState } from "react";
import "../../styles/classification-standards.css";
import { classificationDraftErrorMessage as errorMessage } from "./classificationDraftSelection";
import { useClassificationStandardList } from "./useClassificationStandardList";
import { useStandardLifecycle } from "./useStandardLifecycle";
import { ClassificationStandardDetailState } from "./ClassificationStandardPageStates";

import { navigateHash } from "../../app/hashRouter";
import { AntdProvider } from "../../components/AntdProvider";
import { classificationStandardApi } from "../../shared/api/classificationStandardApi";
import {
  ClassificationStandardDeleteDialog,
  ClassificationStandardRestoreDialog,
} from "./ClassificationStandardDialogs";
import { ClassificationStandardList } from "./ClassificationStandardList";
import { ClassificationStandardWorkspace } from "./ClassificationStandardWorkspace";
import { useClassificationStandardDraftController } from "./useClassificationStandardDraftController";
import { useUnsavedNavigation } from "../../hooks/useUnsavedNavigation";
import { UnsavedChangesDialog } from "../../components/UnsavedChangesActions";

/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardSummary} ClassificationStandardSummary */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardVersion} ClassificationStandardVersion */
/** @typedef {import("../../shared/api/classificationStandardContracts").ClassificationStandardDetail} ClassificationStandardDetail */
/** @typedef {{query: Record<string, string | undefined>}} ClassificationStandardsRoute */
/** @typedef {{route: ClassificationStandardsRoute, notify: (message: string, tone?: string) => void}} ClassificationStandardsPageProps */

/** @param {ClassificationStandardsRoute} route */
function classificationStandardPageMode(route) {
  const selectedId = route.query.standard || "";
  const mode = route.query.view === "new" ? "new" : selectedId ? "edit" : "list";
  return {
    selectedId,
    mode,
    initiallyEditing: route.query.view === "edit" || mode === "new",
    showWorkspace: mode === "new" || mode === "edit",
  };
}

/** @param {{mode: string, selectedId: string, pageLoading: boolean, pageError: {id: string, message: string} | null, detail: ClassificationStandardDetail | null}} state */
function classificationStandardDetailStatus({
  mode,
  selectedId,
  pageLoading,
  pageError,
  detail,
}) {
  const detailError = pageError?.id === selectedId ? pageError.message : "";
  const detailPending =
    mode === "edit" && detail?.id !== selectedId && (pageLoading || !detailError);
  return {
    detailError,
    detailPending,
    showDetailState:
      detailPending || (detailError && mode === "edit" && detail?.id !== selectedId),
  };
}

/** @param {ClassificationStandardsPageProps} props */
export function ClassificationStandardsPage({ route, notify }) {
  const {
    query,
    setQuery,
    statusFilter,
    setStatusFilter,
    loading,
    error: listError,
    hasData,
    loadStandards,
    filteredStandards,
    totals,
  } = useClassificationStandardList(
    notify,
    classificationStandardPageMode(route).mode === "list",
  );
  const [busy, setBusy] = useState("");
  const [deleteTarget, setDeleteTarget] = useState(
    /** @type {ClassificationStandardSummary | null} */ (null),
  );
  const [restoreTarget, setRestoreTarget] = useState(
    /** @type {ClassificationStandardVersion | null} */ (null),
  );

  const { selectedId, mode, initiallyEditing, showWorkspace } =
    classificationStandardPageMode(route);

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

  const lifecycle = useStandardLifecycle({
    detail,
    draft,
    setBusy,
    loadStandards,
    loadSelected,
    notify,
  });
  const exit = useUnsavedNavigation({
    dirty: showWorkspace && dirty,
    busy: showWorkspace && dirty && Boolean(busy),
    save: () => saveDraft(false),
  });

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
      notify("历史内容已暂存，请检查后保存并启用");
    } catch (error) {
      notify(errorMessage(error), "error");
    } finally {
      setBusy("");
    }
  };

  const { detailError, detailPending, showDetailState } =
    classificationStandardDetailStatus({
      mode,
      selectedId,
      pageLoading,
      pageError,
      detail,
    });

  return (
    <AntdProvider>
      <div className="standard-page classification-standard-page">
        {mode === "list" && (
          <ClassificationStandardList
            standards={filteredStandards}
            error={listError}
            hasData={hasData}
            loading={loading}
            onRetry={() =>
              loadStandards().catch((error) => notify(errorMessage(error), "error"))
            }
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

        {showWorkspace &&
          (showDetailState ? (
            <ClassificationStandardDetailState
              pending={detailPending}
              error={detailError}
              onRetry={() =>
                loadSelected(selectedId).catch((error) =>
                  notify(errorMessage(error), "error"),
                )
              }
            />
          ) : (
            <ClassificationStandardWorkspace
              key={selectedId || "new"}
              updating={pageLoading}
              updateError={detailError}
              onRetry={() =>
                loadSelected(selectedId).catch((error) =>
                  notify(errorMessage(error), "error"),
                )
              }
              initiallyEditing={initiallyEditing}
              versions={versions}
              notify={notify}
              onDelete={() => setDeleteTarget(detail)}
              onRestore={setRestoreTarget}
              onEnable={lifecycle.enable}
              onDiscard={lifecycle.discard}
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
              onSave={() => {
                void saveDraft();
              }}
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
        <UnsavedChangesDialog
          guard={exit}
          message="离开前是否暂存本次分类标准修改？暂存不会启用或发布。"
        />
      </div>
    </AntdProvider>
  );
}
