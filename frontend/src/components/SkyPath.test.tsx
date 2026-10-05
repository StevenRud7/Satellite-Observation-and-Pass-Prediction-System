import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SkyPath from "./SkyPath";
import type { PassEvent } from "../types/api";

const PASS: PassEvent = {
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
};

describe("SkyPath", () => {
  it("renders an SVG with the trajectory path and three markers", () => {
    const { container } = render(<SkyPath pass={PASS} />);

    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(container.querySelector(".sky-path__trajectory")).toBeInTheDocument();
    expect(container.querySelectorAll(".sky-path__point").length).toBe(3);
  });
});
