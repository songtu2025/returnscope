import "@testing-library/jest-dom/vitest";

class EventSourceStub {
  addEventListener() {}

  close() {}
}

class ResizeObserverStub {
  observe() {}

  unobserve() {}

  disconnect() {}
}

globalThis.EventSource = EventSourceStub;
globalThis.ResizeObserver = ResizeObserverStub;
globalThis.HTMLElement.prototype.scrollIntoView = () => {};
