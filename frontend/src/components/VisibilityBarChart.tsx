import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { MethodVisibility } from "../types/api";
import { classificationColorVar, methodLabel } from "../utils/format";

interface VisibilityBarChartProps {
  results: MethodVisibility[];
}

function VisibilityBarChart({ results }: VisibilityBarChartProps) {
  const data = results.map((r) => ({
    method: methodLabel(r.method),
    score: r.score,
    color: classificationColorVar(r.classification),
  }));

  return (
    <div className="visibility-bar-chart">
      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis
            type="category"
            dataKey="method"
            stroke="var(--color-text-dim)"
            tick={{ fontSize: 12 }}
            width={80}
          />
          <Tooltip
            formatter={(value: number) => [`${value}/100`, "Score"]}
            contentStyle={{
              backgroundColor: "var(--color-bg-elevated)",
              border: "1px solid var(--color-border)",
              borderRadius: 6,
              fontSize: "0.8rem",
            }}
          />
          <Bar dataKey="score" radius={[0, 4, 4, 0]} barSize={22}>
            {data.map((entry) => (
              <Cell key={entry.method} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default VisibilityBarChart;
