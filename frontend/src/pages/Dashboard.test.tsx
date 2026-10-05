import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Dashboard from "./Dashboard";

const SAMPLE_OPPORTUNITY = {
  norad_id: 25544,
  satellite_name: "ISS (ZARYA)",
  pass_event: {
    rise_time: "2025-01-01T20:00:00Z",
    peak_time: "2025-01-01T20:03:00Z",
    set_time: "2025-01-01T20:06:00Z",
    rise_azimuth_deg: 10,
    peak_azimuth_deg: 90,
    set_azimuth_deg: 170,
    max_elevation_deg: 78,
    duration_seconds: 360,
    rise_range_km: 1500,
    max_range_km: 500,
    set_range_km: 1500,
    min_elevation_threshold_deg: 10,
  },
  visibility: {
    method: "naked_eye",
    score: 94,
    classification: "excellent",
    confidence: "medium",
    factors: [],
    limitations: [],
  },
};

function mockFetchByUrl(handlers: Record<string, () => Promise<unknown>>) {
  return vi.fn((url: string) => {
    const match = Object.keys(handlers).find((pattern) => url.includes(pattern));
    if (!match) return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    return handlers[match]().then((body) => ({ ok: true, status: 200, json: async () => body }));
  });
}

describe("Dashboard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("finds and displays ranked opportunities", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/api/observers": async () => [],
        "/api/satellites/catalog": async () => [],
        "/api/observations/best": async () => [SAMPLE_OPPORTUNITY],
      }),
    );

    render(<Dashboard />);

    fireEvent.click(screen.getByRole("button", { name: /find best opportunities/i }));

    await waitFor(() => expect(screen.getByText("ISS (ZARYA)")).toBeInTheDocument());
    expect(screen.getByText(/94.*Excellent/)).toBeInTheDocument();
  });

  it("shows an error message when the search fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/observers") || url.includes("/api/satellites/catalog")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [] });
        }
        return Promise.resolve({
          ok: false,
          status: 502,
          json: async () => ({ detail: "CelesTrak unreachable" }),
        });
      }),
    );

    render(<Dashboard />);
    fireEvent.click(screen.getByRole("button", { name: /find best opportunities/i }));

    await waitFor(() => expect(screen.getByText("CelesTrak unreachable")).toBeInTheDocument());
  });

  it("opens the mission dossier for a selected opportunity, on the same page", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/api/observers": async () => [],
        "/api/satellites/catalog": async () => [],
        "/api/observations/best": async () => [SAMPLE_OPPORTUNITY],
        "/api/passes/predict": async () => [
          {
            id: 1,
            norad_id: 25544,
            satellite_name: "ISS (ZARYA)",
            observer_id: null,
            pass_event: SAMPLE_OPPORTUNITY.pass_event,
            visibility: [
              {
                method: "naked_eye",
                score: 94,
                classification: "excellent",
                confidence: "medium",
                factors: [],
                limitations: [],
              },
              {
                method: "binoculars",
                score: 98,
                classification: "excellent",
                confidence: "medium",
                factors: [],
                limitations: [],
              },
              {
                method: "telescope",
                score: 80,
                classification: "very_good",
                confidence: "medium",
                factors: [],
                limitations: [],
              },
            ],
          },
        ],
      }),
    );

    render(<Dashboard />);
    fireEvent.click(screen.getByRole("button", { name: /find best opportunities/i }));
    await waitFor(() => expect(screen.getByText("ISS (ZARYA)")).toBeInTheDocument());

    // Placeholder shown before anything is selected.
    expect(screen.getByText(/select a pass from the mission queue/i)).toBeInTheDocument();

    fireEvent.click(
      within(screen.getByText("Mission queue").closest("div")!).getByRole("button", {
        name: /ISS \(ZARYA\)/i,
      }),
    );

    await waitFor(() => expect(screen.getByText("Mission Dossier")).toBeInTheDocument());
    // The dossier is embedded on the same page - the mission queue behind
    // it is still in the document, not replaced by a navigation.
    expect(screen.getByText("Mission queue")).toBeInTheDocument();
  });
});
