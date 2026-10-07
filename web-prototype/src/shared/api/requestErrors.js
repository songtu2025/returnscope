/** @param {unknown} error */
export function errorMessage(error) {
  return error instanceof Error ? error.message : "请求失败";
}

/** @param {unknown} error */
export function errorDetailMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

/** @param {unknown} error */
export function errorStatus(error) {
  return typeof error === "object" && error !== null && "status" in error
    ? error.status
    : undefined;
}
