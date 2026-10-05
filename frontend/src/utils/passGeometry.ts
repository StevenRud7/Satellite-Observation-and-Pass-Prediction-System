/**
 * Shared math for the Phase 9 visualizations.
 *
 * Important scope note: the backend gives us exactly three real,
 * SGP4-derived points per pass - rise, peak, and set (topocentric
 * azimuth/elevation/range). It does not expose a continuous ephemeris
 * (that would need a new backend endpoint, out of scope for this phase).
 * Everything below that produces points *between* rise/peak/set is a
 * smooth, visually reasonable interpolation for display purposes only -
 * not a re-derivation of orbital mechanics on the frontend. This keeps
 * "the browser is not responsible for primary scientific computation"
 * (project plan section 5) intact: the three real points are exact
 * backend output, and everything else is just how we draw a curve
 * through them.
 */
import type { PassEvent } from "../types/api";

export interface AzElPoint {
  /** Seconds since rise, for ordering/interpolation. */
  t: number;
  azimuthDeg: number;
  elevationDeg: number;
  rangeKm: number;
}

/**
 * The three real backend-computed points of a pass, as a time series.
 */
export function passKeyPoints(pass: PassEvent): AzElPoint[] {
  const riseMs = new Date(pass.rise_time).getTime();
  const toSeconds = (iso: string) => (new Date(iso).getTime() - riseMs) / 1000;

  return [
    {
      t: toSeconds(pass.rise_time),
      azimuthDeg: pass.rise_azimuth_deg,
      elevationDeg: pass.min_elevation_threshold_deg,
      rangeKm: pass.rise_range_km,
    },
    {
      t: toSeconds(pass.peak_time),
      azimuthDeg: pass.peak_azimuth_deg,
      elevationDeg: pass.max_elevation_deg,
      rangeKm: pass.max_range_km,
    },
    {
      t: toSeconds(pass.set_time),
      azimuthDeg: pass.set_azimuth_deg,
      elevationDeg: pass.min_elevation_threshold_deg,
      rangeKm: pass.set_range_km,
    },
  ];
}

/** Shortest-path interpolation between two compass bearings (handles the 0/360 wrap). */
function lerpAzimuth(a: number, b: number, frac: number): number {
  const diff = ((b - a + 540) % 360) - 180;
  return (a + diff * frac + 360) % 360;
}

/**
 * Smoothly interpolate az/el/range at `n` points across the whole pass,
 * by fitting each of the two legs (rise->peak, peak->set) with a curve
 * that matches the known endpoints - elevation rises and falls roughly
 * like a sine hump in a real pass, so we shape each leg with an
 * ease-in/ease-out (sine) profile rather than a straight line, purely so
 * the charted/drawn curve looks like a real pass rather than a sharp
 * triangle. This is a display approximation, documented above.
 */
export function interpolatePassProfile(pass: PassEvent, pointsPerLeg = 20): AzElPoint[] {
  const [rise, peak, set] = passKeyPoints(pass);
  const points: AzElPoint[] = [];

  const easeInOutSine = (x: number) => 1 - Math.cos((x * Math.PI) / 2);

  for (let i = 0; i <= pointsPerLeg; i++) {
    const frac = i / pointsPerLeg;
    const eased = easeInOutSine(frac);
    points.push({
      t: rise.t + (peak.t - rise.t) * frac,
      azimuthDeg: lerpAzimuth(rise.azimuthDeg, peak.azimuthDeg, frac),
      elevationDeg: rise.elevationDeg + (peak.elevationDeg - rise.elevationDeg) * eased,
      rangeKm: rise.rangeKm + (peak.rangeKm - rise.rangeKm) * frac,
    });
  }
  for (let i = 1; i <= pointsPerLeg; i++) {
    const frac = i / pointsPerLeg;
    const eased = easeInOutSine(frac);
    points.push({
      t: peak.t + (set.t - peak.t) * frac,
      azimuthDeg: lerpAzimuth(peak.azimuthDeg, set.azimuthDeg, frac),
      elevationDeg: peak.elevationDeg + (set.elevationDeg - peak.elevationDeg) * eased,
      rangeKm: peak.rangeKm + (set.rangeKm - peak.rangeKm) * frac,
    });
  }
  return points;
}
