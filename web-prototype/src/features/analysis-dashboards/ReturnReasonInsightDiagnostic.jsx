import { useState } from "react";
import { analysisContextTerms } from "./analysisContextPresentation";
import { ReturnReasonDiagnosticHeader } from "./ReturnReasonDiagnosticHeader";
import { ReturnReasonDiagnosticOverview } from "./ReturnReasonDiagnosticOverview";
import { ReturnReasonDiagnosticSemantics } from "./ReturnReasonDiagnosticSemantics";
import { ReturnReasonDiagnosticEvidence } from "./ReturnReasonDiagnosticEvidence";
/** @typedef {import("./analysisDashboardContracts").DashboardInsights} DashboardInsights */
/** @typedef {import("./analysisDashboardContracts").DashboardRecord} DashboardRecord */
/** @typedef {import("./analysisDashboardContracts").DashboardRoute} DashboardRoute */
/** @typedef {import("./analysisDashboardContracts").InsightEvidence} InsightEvidence */
/** @typedef {import("./analysisDashboardContracts").InsightProduct} InsightProduct */
/** @typedef {import("./analysisDashboardContracts").InsightReason} InsightReason */
/** @typedef {import("./analysisDashboardContracts").InsightSemanticProfile} InsightSemanticProfile */
/** @typedef {{data: DashboardInsights, selected?: InsightReason, subjectLabel?: string, products: InsightProduct[], coReasons: InsightReason[], semanticProfile: InsightSemanticProfile, evidence: InsightEvidence, evidencePage: number, evidenceLoading: boolean, evidenceError: string, detailLoading?: boolean, detailError?: string, onDetailRetry?: () => void | Promise<void>, analysisContext: string, onUpdateRoute: (changes: Partial<DashboardRoute>) => void, onEvidence: (record: DashboardRecord, trigger: HTMLElement | null) => void, onEvidencePage: (page: number) => void, onEvidenceRetry: () => void}} ReturnReasonInsightDiagnosticProps */

/** @param {ReturnReasonInsightDiagnosticProps} props */
export function ReturnReasonInsightDiagnostic(props) {
  const { selected, detailLoading = false, analysisContext } = props;
  const [showDefinition, setShowDefinition] = useState(false);
  const terms = analysisContextTerms(analysisContext);
  return (
    <main className="return-insight-diagnostic" aria-busy={detailLoading}>
      {selected ? (
        <>
          <ReturnReasonDiagnosticHeader
            {...props}
            selected={selected}
            terms={terms}
            showDefinition={showDefinition}
            onToggleDefinition={() => setShowDefinition((visible) => !visible)}
          />
          <ReturnReasonDiagnosticOverview
            data={props.data}
            selected={selected}
            products={props.products}
            terms={terms}
            onUpdateRoute={props.onUpdateRoute}
          />
          <ReturnReasonDiagnosticSemantics
            semanticProfile={props.semanticProfile}
            coReasons={props.coReasons}
            onUpdateRoute={props.onUpdateRoute}
          />
          <ReturnReasonDiagnosticEvidence
            {...props}
            selected={selected}
            terms={terms}
          />
        </>
      ) : (
        <div className="return-insight-empty return-diagnostic-empty">
          {terms.selectReasonPrompt}
        </div>
      )}
    </main>
  );
}
