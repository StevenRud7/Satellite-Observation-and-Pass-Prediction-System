import { describe, expect, it } from "vitest";

import { interpolatePassProfile, passKeyPoints } from "./passGeometry";
import type { PassEvent } from "../types/api";

function makePass(overrides: Partial<PassEvent> = {}): PassEvent {
  return {
    rise_time: "2025-01-01T20:00:00Z",
    peak_time: "2025-01-01T20:03:00Z",
    set_time: "2025-01-01T20:06:00Z",
    rise_azimuth_deg: 350,
    peak_azimuth_deg: 10,
    set_azimuth_deg: 30,
    max_elevation_deg: 80,
    duration_seconds: 360,
    rise_range_km: 1500,
    max_range_km: 500,
    set_range_km: 1500,
    min_elevation_threshold_deg: 10,
    ...overrides,
  };
}

describe("passKeyPoints", () => {
  it("extracts rise/peak/set with correct relative timing", () => {
    const [rise, peak, set] = passKeyPoints(makePass());
    expect(rise.t).toBe(0);
    expect(peak.t).toBe(180);
    expect(set.t).toBe(360);
    expect(rise.elevationDeg).toBe(10);
    expect(peak.elevationDeg).toBe(80);
  });
});

describe("interpolatePassProfile", () => {
  it("starts at rise and ends at set", () => {
    const pass = makePass();
    const profile = interpolatePassProfile(pass, 10);
    expect(profile[0].elevationDeg).toBeCloseTo(10);
    expect(profile[profile.length - 1].elevationDeg).toBeCloseTo(10);
  });

  it("reaches (approximately) the peak elevation partway through", () => {
    const profile = interpolatePassProfile(makePass(), 10);
    const maxElevation = Math.max(...profile.map((p) => p.elevationDeg));
    expect(maxElevation).toBeCloseTo(80, 0);
  });

  it("interpolates azimuth across the 350deg -> 10deg wraparound without a 340deg jump", () => {
    // rise=350, peak=10: the short way is +20 degrees (through 360/0), not
    // the long way through 180. Every step should move by a small amount.
    const profile = interpolatePassProfile(makePass(), 20);
    const firstLeg = profile.slice(0, 21).map((p) => p.azimuthDeg);

    for (let i = 1; i < firstLeg.length; i++) {
      const delta = Math.abs(((firstLeg[i] - firstLeg[i - 1] + 540) % 360) - 180);
      expect(delta).toBeLessThan(5);
    }
  });
});
