/** @param {unknown} error */
export function errorName(error) {
  return error instanceof Error ? error.name : "";
}

/** @param {unknown} error */
export function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

export { errorStatus } from "../../shared/api/requestErrors";
