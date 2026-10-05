import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver, but Recharts' ResponsiveContainer
// and our own Globe3D component both use it. A minimal no-op stand-in is
// enough for tests, which don't rely on real resize events.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// jsdom doesn't implement scrollIntoView either; Dashboard.tsx calls it to
// bring the mission queue into view when a search starts.
if (typeof Element.prototype.scrollIntoView === "undefined") {
  Element.prototype.scrollIntoView = () => {};
}
