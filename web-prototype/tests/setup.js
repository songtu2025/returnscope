import "@testing-library/jest-dom/vitest";

class EventSourceStub {
  addEventListener() {}

  close() {}
}

globalThis.EventSource = EventSourceStub;
globalThis.HTMLElement.prototype.scrollIntoView = () => {};
