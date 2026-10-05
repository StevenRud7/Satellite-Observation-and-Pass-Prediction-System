import { lazy, Suspense, useEffect, useState } from "react";

import { ApiError, predictPasses } from "../api/client";
import ClassificationBadge from "./ClassificationBadge";
import ElevationChart from "./ElevationChart";
import type { Location } from "./LocationForm";
import PassTimeline from "./PassTimeline";
import SkyPath from "./SkyPath";
import VisibilityBarChart from "./VisibilityBarChart";
import type {
  MethodVisibility,
  ObservationMethod,
  PassEvent,
  PassWithVisibility,
  RankedOpportunity,
} from "../types/api";
import { formatDegrees, formatDuration, formatTime, methodLabel } from "../utils/format";

// Three.js is a large dependency - only load it when the 3D tab is
// actually opened, rather than paying that cost whenever a dossier opens.
const Globe3D = lazy(() => import("./Globe3D"));

interface PassDossierProps {
  opportunity: RankedOpportunity;
  location: Location;
  onClose: () => void;
}

// A small buffer around the already-known rise/set times guarantees the
// same pass is found deterministically, rather than relying on "now"
// matching whatever the ranking call used server-side.
const BUFFER_MINUTES = 5;

/**
 * A single pass, laid out as a "mission dossier": a headline mission
 * patch (see ClassificationBadge variant="patch"), the rise/peak/set
 * timeline, and the three observation-method assessments with their
 * "why" explanations. Rendered inline in the mission-control dossier
 * panel (see Dashboard.tsx) rather than as a separate page/route - the
 * whole app is a single page (see App.tsx / Dashboard.tsx).
 */
function PassDossier({ opportunity, location, onClose }: PassDossierProps) {
  const [pass, setPass] = useState<PassWithVisibility | null>(null);
  const [selectedMethod, setSelectedMethod] = useState<ObservationMethod>(
    opportunity.visibility.method,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const rise = new Date(opportunity.pass_event.rise_time);
    const set = new Date(opportunity.pass_event.set_time);
    const start = new Date(rise.getTime() - BUFFER_MINUTES * 60_000).toISOString();
    const end = new Date(set.getTime() + BUFFER_MINUTES * 60_000).toISOString();

    setPass(null);
    setSelectedMethod(opportunity.visibility.method);
    setLoading(true);
    setError(null);
    predictPasses({
      norad_id: opportunity.norad_id,
      ...(location.observerId !== null
        ? { observer_id: location.observerId }
        : {
            latitude_deg: location.latitudeDeg,
            longitude_deg: location.longitudeDeg,
            altitude_m: location.altitudeM,
            observer_name: location.name ?? undefined,
          }),
      start,
      end,
      min_elevation_deg: opportunity.pass_event.min_elevation_threshold_deg,
    })
      .then((passes) => {
        if (passes.length === 0) {
          setError("This pass could no longer be found - it may have just occurred.");
          return;
        }
        setPass(passes[0]);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load pass details.");
      })
      .finally(() => setLoading(false));
  }, [opportunity, location]);

  return (
    <div className="card dossier-panel">
      <div className="dossier-panel__header">
        <div>
          <p className="dossier-panel__eyebrow label-caps">Mission Dossier</p>
          <h2 className="dossier-panel__title">{opportunity.satellite_name}</h2>
          <p className="dossier-panel__designation readout">DESIGNATION #{opportunity.norad_id}</p>
        </div>
        <ClassificationBadge
          classification={opportunity.visibility.classification}
          score={opportunity.visibility.score}
          variant="patch"
        />
        <button type="button" className="btn btn--ghost dossier-panel__close" onClick={onClose}>
          Close ✕
        </button>
      </div>

      {loading && <p className="spinner-text">Loading pass details...</p>}
      {error && <p className="error-text">{error}</p>}

      {pass && (
        <>
          <div className="spectral-divider" aria-hidden="true" />
          <PassTimeline pass={pass.pass_event} />
          <PassSummary pass={pass} />
          <PassViews
            pass={pass.pass_event}
            observerLatDeg={location.latitudeDeg}
            observerLonDeg={location.longitudeDeg}
          />
          <VisibilityComparison
            results={pass.visibility}
            selectedMethod={selectedMethod}
            onSelectMethod={setSelectedMethod}
          />
        </>
      )}
    </div>
  );
}

type ViewTab = "sky" | "globe" | "elevation";

function PassViews({
  pass,
  observerLatDeg,
  observerLonDeg,
}: {
  pass: PassEvent;
  observerLatDeg: number;
  observerLonDeg: number;
}) {
  const [tab, setTab] = useState<ViewTab>("sky");
  const tabs: { id: ViewTab; label: string }[] = [
    { id: "sky", label: "Sky Path" },
    { id: "globe", label: "3D View" },
    { id: "elevation", label: "Elevation Graph" },
  ];

  return (
    <div className="card">
      <div className="view-tabs btn-group">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className="btn btn-group__option"
            aria-pressed={tab === t.id}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "sky" && <SkyPath pass={pass} />}
      {tab === "globe" && (
        <Suspense fallback={<p className="spinner-text">Loading 3D view...</p>}>
          <Globe3D observerLatDeg={observerLatDeg} observerLonDeg={observerLonDeg} pass={pass} />
        </Suspense>
      )}
      {tab === "elevation" && <ElevationChart pass={pass} />}
    </div>
  );
}

function PassSummary({ pass }: { pass: PassWithVisibility }) {
  const { pass_event: p } = pass;
  return (
    <div className="card pass-summary">
      <div className="pass-summary__item">
        <span className="field__label">Rise</span>
        <strong className="readout">
          {formatTime(p.rise_time)} · {formatDegrees(p.rise_azimuth_deg)}
        </strong>
      </div>
      <div className="pass-summary__item">
        <span className="field__label">Peak</span>
        <strong className="readout">
          {formatTime(p.peak_time)} · {formatDegrees(p.peak_azimuth_deg)} ·{" "}
          {formatDegrees(p.max_elevation_deg)} elevation
        </strong>
      </div>
      <div className="pass-summary__item">
        <span className="field__label">Set</span>
        <strong className="readout">
          {formatTime(p.set_time)} · {formatDegrees(p.set_azimuth_deg)}
        </strong>
      </div>
      <div className="pass-summary__item">
        <span className="field__label">Duration</span>
        <strong className="readout">{formatDuration(p.duration_seconds)}</strong>
      </div>
      <div className="pass-summary__item">
        <span className="field__label">Closest range</span>
        <strong className="readout">{Math.round(p.max_range_km)} km</strong>
      </div>
    </div>
  );
}

function VisibilityComparison({
  results,
  selectedMethod,
  onSelectMethod,
}: {
  results: MethodVisibility[];
  selectedMethod: ObservationMethod;
  onSelectMethod: (method: ObservationMethod) => void;
}) {
  const selected = results.find((r) => r.method === selectedMethod) ?? results[0];

  return (
    <div className="card">
      <h3 className="section-title">Observation suitability</h3>
      <p className="help-text">
        A heuristic ranking of observing conditions, not a probability of successfully seeing the
        satellite.
      </p>

      <div className="method-comparison">
        {results.map((result) => (
          <button
            key={result.method}
            type="button"
            className="method-comparison__option"
            aria-pressed={result.method === selected.method}
            onClick={() => onSelectMethod(result.method)}
          >
            <span>{methodLabel(result.method)}</span>
            <ClassificationBadge classification={result.classification} score={result.score} />
          </button>
        ))}
      </div>

      <VisibilityBarChart results={results} />

      {selected && (
        <div className="why-panel">
          <h4>Why</h4>
          <ul>
            {selected.factors.map((factor) => (
              <li key={factor.label}>
                <strong>{factor.label}:</strong> {factor.detail}
              </li>
            ))}
          </ul>
          <p className="help-text">Confidence: {selected.confidence}</p>
          {selected.limitations.map((limitation) => (
            <p className="help-text" key={limitation}>
              {limitation}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export default PassDossier;
