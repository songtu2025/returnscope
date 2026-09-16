import type {
  ClassificationResultDrilldownResponse,
  GetDrilldownApiClassificationResultsVersionIdDrilldownGetData,
  GetDrilldownApiClassificationResultsVersionIdDrilldownGetResponse,
  GetResultApiClassificationResultsVersionIdGetData,
  GetResultApiClassificationResultsVersionIdGetResponse,
  GetResultVersionsApiClassificationResultsVersionIdVersionsGetData,
  GetResultVersionsApiClassificationResultsVersionIdVersionsGetResponse,
  GetSummaryApiClassificationResultsVersionIdSummaryGetData,
  GetSummaryApiClassificationResultsVersionIdSummaryGetResponse,
  ListRecordsApiClassificationResultsVersionIdRecordsGetData,
  ListRecordsApiClassificationResultsVersionIdRecordsGetResponse,
  ListResultsApiClassificationResultsGetData,
  ListResultsApiClassificationResultsGetResponse,
} from "./generated/classification-results/types.gen";
import { API_BASE, queryString, request } from "./request";

type ClassificationResultFilters = NonNullable<
  ListResultsApiClassificationResultsGetData["query"]
>;
type ClassificationResultRecordFilters = NonNullable<
  ListRecordsApiClassificationResultsVersionIdRecordsGetData["query"]
>;
type ClassificationResultDrilldownFilters = Omit<
  NonNullable<GetDrilldownApiClassificationResultsVersionIdDrilldownGetData["query"]>,
  "group_by"
>;

export const resultApi = {
  classificationResults: (
    filters: ClassificationResultFilters = {},
    options: RequestInit = {},
  ): Promise<ListResultsApiClassificationResultsGetResponse> =>
    request(`/api/classification-results${queryString({ ...filters })}`, options),
  classificationResult: (
    versionId: GetResultApiClassificationResultsVersionIdGetData["path"]["version_id"],
    options: RequestInit = {},
  ): Promise<GetResultApiClassificationResultsVersionIdGetResponse> =>
    request(`/api/classification-results/${versionId}`, options),
  classificationResultVersions: (
    versionId: GetResultVersionsApiClassificationResultsVersionIdVersionsGetData["path"]["version_id"],
    options: RequestInit = {},
  ): Promise<GetResultVersionsApiClassificationResultsVersionIdVersionsGetResponse> =>
    request(`/api/classification-results/${versionId}/versions`, options),
  classificationResultSummary: (
    versionId: GetSummaryApiClassificationResultsVersionIdSummaryGetData["path"]["version_id"],
    options: RequestInit = {},
  ): Promise<GetSummaryApiClassificationResultsVersionIdSummaryGetResponse> =>
    request(`/api/classification-results/${versionId}/summary`, options),
  classificationResultRecords: (
    versionId: ListRecordsApiClassificationResultsVersionIdRecordsGetData["path"]["version_id"],
    filters: ClassificationResultRecordFilters = {},
    options: RequestInit = {},
  ): Promise<ListRecordsApiClassificationResultsVersionIdRecordsGetResponse> =>
    request(
      `/api/classification-results/${versionId}/records${queryString({ ...filters })}`,
      options,
    ),
  classificationResultDrilldown: (
    versionId: GetDrilldownApiClassificationResultsVersionIdDrilldownGetData["path"]["version_id"],
    groupBy: ClassificationResultDrilldownResponse["group_by"],
    filters: ClassificationResultDrilldownFilters = {},
    options: RequestInit = {},
  ): Promise<GetDrilldownApiClassificationResultsVersionIdDrilldownGetResponse> =>
    request(
      `/api/classification-results/${versionId}/drilldown${queryString({
        group_by: groupBy,
        ...filters,
      })}`,
      options,
    ),
  classificationResultDownloadUrl: (
    versionId: GetResultApiClassificationResultsVersionIdGetData["path"]["version_id"],
  ): string => `${API_BASE}/api/classification-results/${versionId}/download`,
};
