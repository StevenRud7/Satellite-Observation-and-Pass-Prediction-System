import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PassDossier from "./PassDossier";
import type { PassWithVisibility, RankedOpportunity } from "../types/api";

const OPPORTUNITY: RankedOpportunity = {
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

const PASS_WITH_VISIBILITY: PassWithVisibility = {
  id: 1,
  norad_id: 25544,
  satellite_name: "ISS (ZARYA)",
  observer_id: 1,
  pass_event: OPPORTUNITY.pass_event,
  visibility: [
    {
      method: "naked_eye",
      score: 94,
      classification: "excellent",
      confidence: "medium",
      factors: [{ label: "Maximum elevation", detail: "78°" }],
      limitations: [],
    },
    {
      method: "binoculars",
      score: 98,
      classification: "excellent",
      confidence: "medium",
      factors: [{ label: "Maximum elevation", detail: "78°" }],
      limitations: [],
    },
    {
      method: "telescope",
      score: 45,
      classification: "difficult",
      confidence: "low",
      factors: [{ label: "Tracking difficulty", detail: "High" }],
      limitations: ["Fast pass."],
    },
  ],
};

const LOCATION = {
  name: null,
  latitudeDeg: 32.08,
  longitudeDeg: 34.78,
  altitudeM: 0,
  observerId: null,
};

describe("PassDossier", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads and displays the pass summary and visibility comparison", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({ ok: true, status: 200, json: async () => [PASS_WITH_VISIBILITY] }),
    );

    render(<PassDossier opportunity={OPPORTUNITY} location={LOCATION} onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/94.*Excellent/)).toBeInTheDocument());
    expect(screen.getByText(/98.*Excellent/)).toBeInTheDocument();
    expect(screen.getByText(/45.*Difficult/)).toBeInTheDocument();

    // Switching to telescope should show its own factors.
    fireEvent.click(screen.getByText("Telescope"));
    expect(screen.getByText(/Tracking difficulty/)).toBeInTheDocument();
  });

  it("shows an error message if the pass can no longer be found", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }),
    );

    render(<PassDossier opportunity={OPPORTUNITY} location={LOCATION} onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByText(/could no longer be found/i)).toBeInTheDocument());
  });

  it("calls onClose when the close control is used", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({ ok: true, status: 200, json: async () => [PASS_WITH_VISIBILITY] }),
    );
    const onClose = vi.fn();

    render(<PassDossier opportunity={OPPORTUNITY} location={LOCATION} onClose={onClose} />);
    await waitFor(() => expect(screen.getByText(/94.*Excellent/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
