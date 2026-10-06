/**
 * @template Value, Result
 * @param {import("react").RefObject<AbortController | null>} controllerRef
 * @param {(signal: AbortSignal) => Promise<Value>} loadValue
 * @param {(value: Value) => Result} project
 * @returns {Promise<Result | undefined>}
 */
export async function runResultRequest(controllerRef, loadValue, project) {
  controllerRef.current?.abort();
  const controller = new AbortController();
  controllerRef.current = controller;
  try {
    const value = await loadValue(controller.signal);
    return project(value);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") return undefined;
    throw error;
  } finally {
    if (controllerRef.current === controller) {
      controllerRef.current = null;
    }
  }
}
