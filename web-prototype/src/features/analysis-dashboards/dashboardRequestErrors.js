/** @param {unknown} error */
export function errorName(error) {
  return error instanceof Error ? error.name : "";
}

/** @param {unknown} error */
export function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

/** @param {unknown} error */
export function errorStatus(error) {
  return typeof error === "object" && error !== null && "status" in error
    ? error.status
    : undefined;
}
