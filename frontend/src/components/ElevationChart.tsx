import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { PassEvent } from "../types/api";
import { interpolatePassProfile } from "../utils/passGeometry";

interface ElevationChartProps {
  pass: PassEvent;
}

function ElevationChart({ pass }: ElevationChartProps) {
  const data = interpolatePassProfile(pass).map((p) => ({
    minutes: Number((p.t / 60).toFixed(2)),
    elevation: Number(p.elevationDeg.toFixed(1)),
  }));

  return (
    <div className="elevation-chart">
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <defs>
            <linearGradient id="elevationFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.5} />
              <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="minutes"
            stroke="var(--color-text-dim)"
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => `${v.toFixed(0)}m`}
          />
          <YAxis
            domain={[0, 90]}
            ticks={[0, 30, 60, 90]}
            stroke="var(--color-text-dim)"
            tick={{ fontSize: 11 }}
            width={32}
          />
          <Tooltip
            formatter={(value: number) => [`${value.toFixed(0)}°`, "Elevation"]}
            labelFormatter={(v: number) => `${v.toFixed(1)} min after rise`}
            contentStyle={{
              backgroundColor: "var(--color-bg-elevated)",
              border: "1px solid var(--color-border)",
              borderRadius: 6,
              fontSize: "0.8rem",
            }}
          />
          <Area
            type="monotone"
            dataKey="elevation"
            stroke="var(--color-accent)"
            fill="url(#elevationFill)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export default ElevationChart;
