import { createElement } from "react";
import { render } from "@testing-library/react";
import { SWRConfig } from "swr";

const testServerStateConfig = {
  provider: () => new Map(),
  dedupingInterval: 0,
  shouldRetryOnError: false,
};

/** @param {{children: import("react").ReactNode}} props */
function TestServerStateProvider({ children }) {
  return createElement(SWRConfig, { value: testServerStateConfig }, children);
}

/** @type {typeof render} */
export function renderWithServerState(ui, options) {
  return render(ui, { wrapper: TestServerStateProvider, ...options });
}
