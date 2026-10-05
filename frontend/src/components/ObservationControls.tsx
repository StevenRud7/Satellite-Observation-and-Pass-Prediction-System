import type { ObservationMethod } from "../types/api";

export interface ObservationSettings {
  method: ObservationMethod;
  withinHours: number;
  minElevationDeg: number;
}

interface ObservationControlsProps {
  settings: ObservationSettings;
  onChange: (settings: ObservationSettings) => void;
}

const METHOD_OPTIONS: { value: ObservationMethod; label: string }[] = [
  { value: "naked_eye", label: "Naked Eye" },
  { value: "binoculars", label: "Binoculars" },
  { value: "telescope", label: "Telescope" },
];

const WINDOW_OPTIONS: { hours: number; label: string }[] = [
  { hours: 12, label: "Tonight" },
  { hours: 24, label: "Next 24 hours" },
  { hours: 72, label: "Next 3 days" },
];

function ObservationControls({ settings, onChange }: ObservationControlsProps) {
  return (
    <div className="card">
      <h2 className="section-title">Observation preferences</h2>

      <div className="field">
        <span className="field__label">Viewing method</span>
        <div className="btn-group">
          {METHOD_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className="btn btn-group__option"
              aria-pressed={settings.method === option.value}
              onClick={() => onChange({ ...settings, method: option.value })}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <span className="field__label">Time window</span>
        <div className="btn-group">
          {WINDOW_OPTIONS.map((option) => (
            <button
              key={option.hours}
              type="button"
              className="btn btn-group__option"
              aria-pressed={settings.withinHours === option.hours}
              onClick={() => onChange({ ...settings, withinHours: option.hours })}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label className="field__label" htmlFor="min-elevation">
          Minimum elevation ({settings.minElevationDeg}°)
        </label>
        <input
          id="min-elevation"
          type="range"
          min={0}
          max={60}
          step={5}
          value={settings.minElevationDeg}
          onChange={(e) => onChange({ ...settings, minElevationDeg: Number(e.target.value) })}
        />
        <p className="help-text">
          Passes that never rise above this height above the horizon are excluded.
        </p>
      </div>
    </div>
  );
}

export default ObservationControls;
