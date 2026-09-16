import { auditApi } from "./shared/api/auditApi";
import { classificationStandardApi } from "./shared/api/classificationStandardApi";
import { dataApi } from "./shared/api/dataApi";
import { dashboardApi } from "./shared/api/dashboardApi";
import { modelApi } from "./shared/api/modelApi";
import { ApiError } from "./shared/api/request";
import { resultApi } from "./shared/api/resultApi";
import { reviewApi } from "./shared/api/reviewApi";
import { reviewBatchApi } from "./shared/api/reviewBatchApi";
import { taskApi } from "./shared/api/taskApi";
import { teamApi } from "./shared/api/teamApi";
import { workbenchApi } from "./shared/api/workbenchApi";

export { ApiError };

// 兼容现有页面；新代码按领域直接导入对应 API。
export const api = {
  ...auditApi,
  ...classificationStandardApi,
  ...teamApi,
  ...dataApi,
  ...dashboardApi,
  ...modelApi,
  ...taskApi,
  ...resultApi,
  ...reviewApi,
  ...reviewBatchApi,
  ...workbenchApi,
};
