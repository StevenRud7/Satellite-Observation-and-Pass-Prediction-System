import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

function mockFetchByUrl(handlers: Record<string, () => Promise<unknown>>) {
  return vi.fn((url: string) => {
    const match = Object.keys(handlers).find((pattern) => url.includes(pattern));
    if (!match) return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    return handlers[match]().then((body) => ({ ok: true, status: 200, json: async () => body }));
  });
}

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows Online once the backend health check succeeds, and renders the app as a single page", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/health": async () => ({ status: "ok", service: "x", timestamp: "2025-01-01T00:00:00Z" }),
        "/api/observers": async () => [],
        "/api/satellites/catalog": async () => [],
      }),
    );

    render(<App />);

    expect(screen.getByText("Checking...")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Online")).toBeInTheDocument());

    // Location, satellite picker, preferences, and the mission queue are
    // all visible together - there's no separate page/route to navigate to.
    expect(screen.getByText("Your location")).toBeInTheDocument();
    expect(screen.getByText("Satellites to consider")).toBeInTheDocument();
    expect(screen.getByText("Mission queue")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /find best opportunities/i })).toBeInTheDocument();

    // No visible sign of build/phase progression anywhere on the page.
    expect(screen.queryByText(/phase \d/i)).not.toBeInTheDocument();
  });

  it("shows Offline when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    render(<App />);

    await waitFor(() => expect(screen.getByText("Offline")).toBeInTheDocument());
  });
});
