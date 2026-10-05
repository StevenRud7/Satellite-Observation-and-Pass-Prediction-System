import type { VisibilityClassification } from "../types/api";
import { classificationColorVar, classificationLabel } from "../utils/format";

interface ClassificationBadgeProps {
  classification: VisibilityClassification;
  score: number;
  /**
   * "pill" (default): compact inline badge for list rows.
   * "patch": larger circular "mission patch" badge for dossier headers -
   * see the 70s-poster/mission-patch aesthetic in shared.css `.mission-patch`.
   */
  variant?: "pill" | "patch";
}

function ClassificationBadge({
  classification,
  score,
  variant = "pill",
}: ClassificationBadgeProps) {
  const color = classificationColorVar(classification);

  if (variant === "patch") {
    return (
      <span
        className="mission-patch"
        style={{
          border: `2px solid ${color}`,
          background: `radial-gradient(circle at 50% 35%, color-mix(in srgb, ${color} 35%, transparent), transparent 75%)`,
          color,
        }}
      >
        <span className="mission-patch__score">{score}</span>
        <span className="mission-patch__label">{classificationLabel(classification)}</span>
      </span>
    );
  }

  return (
    <span
      className="badge"
      style={{ backgroundColor: `color-mix(in srgb, ${color} 22%, transparent)`, color }}
    >
      {score} · {classificationLabel(classification)}
    </span>
  );
}

export default ClassificationBadge;
