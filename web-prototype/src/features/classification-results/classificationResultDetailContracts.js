/** @typedef {import("../../shared/api/generated/classification-results/types.gen").ClassificationResultGroupResponse} ClassificationResultGroup */
/** @typedef {import("./classificationResultRoute").ClassificationResultRoute} ClassificationResultRoute */
/**
 * @typedef {object} ClassificationResultDetailProps
 * @property {ClassificationResultRoute} route
 * @property {(changes: Partial<ClassificationResultRoute>) => void} updateRoute
 * @property {(message: string, tone?: string) => void} notify
 * @property {string} userId
 */
/** @typedef {ReturnType<typeof import("./useClassificationResultDetailData").useClassificationResultDetailData>} ResultDetailData */
/** @typedef {ClassificationResultDetailProps & Omit<ResultDetailData,"result"> & {result:NonNullable<ResultDetailData["result"]>,orderInput:string,setOrderInput:import("react").Dispatch<import("react").SetStateAction<string>>,selectedGroup:ClassificationResultGroup|null,closeEvidence:()=>void,openEvidence:(group:ClassificationResultGroup)=>(trigger:HTMLButtonElement)=>void,evidenceTriggerRef:import("react").RefObject<HTMLButtonElement|null>,createDashboardFromResult:()=>void,openOrderRecords:()=>void}} ResultDetailViewProps */
/** @typedef {ResultDetailViewProps & ReturnType<typeof import("./resultDetailPresentation").resultDetailPresentation> & ReturnType<typeof import("./resultDetailActions").resultDetailActions>} ResultDetailContext */
export {};
