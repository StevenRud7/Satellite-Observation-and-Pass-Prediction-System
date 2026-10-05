import type { PassEvent } from "../types/api";
import { interpolatePassProfile, passKeyPoints } from "../utils/passGeometry";

interface SkyPathProps {
  pass: PassEvent;
}

const SIZE = 280;
const CENTER = SIZE / 2;
const RADIUS = SIZE / 2 - 28;

/** Polar projection: azimuth clockwise from North (top), elevation 90° at
 * center (zenith) to 0° at the rim (horizon) - the same convention used
 * by most amateur pass-prediction sky charts. */
function project(azimuthDeg: number, elevationDeg: number): { x: number; y: number } {
  const r = (RADIUS * (90 - Math.max(0, Math.min(90, elevationDeg)))) / 90;
  const theta = (azimuthDeg * Math.PI) / 180;
  return { x: CENTER + r * Math.sin(theta), y: CENTER - r * Math.cos(theta) };
}

function toPathD(points: { x: number; y: number }[]): string {
  return points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");
}

function SkyPath({ pass }: SkyPathProps) {
  const profile = interpolatePassProfile(pass).map((p) => project(p.azimuthDeg, p.elevationDeg));
  const [rise, peak, set] = passKeyPoints(pass).map((p) => project(p.azimuthDeg, p.elevationDeg));

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      role="img"
      aria-label="Sky path of the pass"
      className="sky-path"
    >
      {[0, 30, 60].map((elevation) => (
        <circle
          key={elevation}
          cx={CENTER}
          cy={CENTER}
          r={(RADIUS * (90 - elevation)) / 90}
          className="sky-path__ring"
        />
      ))}

      <text x={CENTER} y={14} className="sky-path__label" textAnchor="middle">
        N
      </text>
      <text x={SIZE - 10} y={CENTER + 4} className="sky-path__label" textAnchor="middle">
        E
      </text>
      <text x={CENTER} y={SIZE - 6} className="sky-path__label" textAnchor="middle">
        S
      </text>
      <text x={10} y={CENTER + 4} className="sky-path__label" textAnchor="middle">
        W
      </text>

      <path d={toPathD(profile)} className="sky-path__trajectory" fill="none" />

      <circle cx={rise.x} cy={rise.y} r={4} className="sky-path__point sky-path__point--rise" />
      <circle cx={peak.x} cy={peak.y} r={5} className="sky-path__point sky-path__point--peak" />
      <circle cx={set.x} cy={set.y} r={4} className="sky-path__point sky-path__point--set" />
    </svg>
  );
}

export default SkyPath;
