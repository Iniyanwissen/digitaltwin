import "@testing-library/jest-dom/vitest";

// jsdom has no canvas or ResizeObserver; the live screen degrades to no-op drawing in tests.
HTMLCanvasElement.prototype.getContext = (() => null) as unknown as HTMLCanvasElement["getContext"];

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
