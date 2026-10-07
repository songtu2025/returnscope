/** @param {unknown} error */
export function errorName(error) {
  return error instanceof Error ? error.name : "";
}

export {
  errorDetailMessage as errorMessage,
  errorStatus,
} from "../../shared/api/requestErrors";
