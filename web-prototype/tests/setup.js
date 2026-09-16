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
globalThis.matchMedia = (media) => ({
  matches: false,
  media,
  onchange: null,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {
    return false;
  },
});
globalThis.HTMLElement.prototype.scrollIntoView = () => {};
