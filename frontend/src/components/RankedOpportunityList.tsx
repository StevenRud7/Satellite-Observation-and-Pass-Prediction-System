import type { RankedOpportunity } from "../types/api";
import { formatDegrees, formatDuration, formatTime, opportunityKey } from "../utils/format";
import ClassificationBadge from "./ClassificationBadge";

interface RankedOpportunityListProps {
  opportunities: RankedOpportunity[];
  selectedKey: string | null;
  onSelect: (opportunity: RankedOpportunity) => void;
}

function RankedOpportunityList({
  opportunities,
  selectedKey,
  onSelect,
}: RankedOpportunityListProps) {
  if (opportunities.length === 0) {
    return (
      <div className="card">
        <p className="help-text">
          No qualifying passes found. Try a wider time window, a lower minimum elevation, or a
          different satellite.
        </p>
      </div>
    );
  }

  return (
    <ol className="opportunity-list">
      {opportunities.map((opportunity, index) => {
        const { pass_event: pass, visibility } = opportunity;
        const key = opportunityKey(opportunity);
        return (
          <li key={key}>
            <button
              type="button"
              className="opportunity-card"
              aria-pressed={selectedKey === key}
              onClick={() => onSelect(opportunity)}
            >
              <span className="opportunity-card__rank readout">{index + 1}</span>
              <span className="opportunity-card__body">
                <span className="opportunity-card__header">
                  <h3>{opportunity.satellite_name}</h3>
                  <ClassificationBadge
                    classification={visibility.classification}
                    score={visibility.score}
                  />
                </span>
                <span className="opportunity-card__designation">
                  DESIGNATION #{opportunity.norad_id}
                </span>
                <span className="opportunity-card__stats">
                  {formatTime(pass.rise_time)} &ndash; {formatTime(pass.set_time)} &middot; max{" "}
                  {formatDegrees(pass.max_elevation_deg)} &middot;{" "}
                  {formatDuration(pass.duration_seconds)}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export default RankedOpportunityList;
