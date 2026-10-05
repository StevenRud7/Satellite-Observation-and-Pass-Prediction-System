import { useRef, useState } from "react";

import { ApiError, bestObservations } from "../api/client";
import LocationForm, { type Location } from "../components/LocationForm";
import ObservationControls, { type ObservationSettings } from "../components/ObservationControls";
import PassDossier from "../components/PassDossier";
import RankedOpportunityList from "../components/RankedOpportunityList";
import SatellitePicker, { type TrackedSatellite } from "../components/SatellitePicker";
import type { RankedOpportunity } from "../types/api";
import { opportunityKey } from "../utils/format";

// Singapore: chosen as the default location because it maximizes the
// chance of a first-time visitor immediately seeing real results. It's
// close to the equator (1.35°N), so it falls within every catalog
// satellite's visible-latitude band (even Hubble's relatively narrow
// ±28.47°) rather than sitting near the edge of one - and it's a
// globally well-known city, so the default doesn't feel arbitrary.
const DEFAULT_LOCATION: Location = {
  name: "Singapore",
  latitudeDeg: 1.3521,
  longitudeDeg: 103.8198,
  altitudeM: 15,
  observerId: null,
};

const DEFAULT_SATELLITES: TrackedSatellite[] = [{ noradId: 25544, name: "ISS (ZARYA)" }];

const DEFAULT_SETTINGS: ObservationSettings = {
  method: "naked_eye",
  withinHours: 24,
  minElevationDeg: 10,
};

// The ranking API allows up to 100 results per request; asking for the
// max here is how the mission queue shows every qualifying pass rather
// than an arbitrarily short top-N list.
const MAX_RESULTS = 100;

/**
 * The whole app, as a single page ("mission control"): a row of control
 * cards (location, satellite picker, preferences) sits on top so all
 * three are visible together, the mission queue lists every qualifying
 * pass right below it, and the selected pass's dossier opens alongside
 * the queue - no page navigation. See styles/dashboard.css
 * `.mission-control` for the responsive layout, which reflows to a
 * single stacked column (controls -> button -> queue -> dossier) on
 * narrow/mobile screens.
 */
function Dashboard() {
  const [location, setLocation] = useState<Location>(DEFAULT_LOCATION);
  const [satellites, setSatellites] = useState<TrackedSatellite[]>(DEFAULT_SATELLITES);
  const [settings, setSettings] = useState<ObservationSettings>(DEFAULT_SETTINGS);

  const [results, setResults] = useState<RankedOpportunity[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<RankedOpportunity | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<Location | null>(null);

  const resultsRef = useRef<HTMLDivElement | null>(null);

  async function findBestOpportunities(): Promise<void> {
    if (satellites.length === 0) {
      setError("Add at least one satellite to search.");
      return;
    }

    // Jump straight to the mission queue as soon as the search starts,
    // not once it finishes - on a small screen (or a tall control
    // section) it can be well below the fold, and this is what shows the
    // person their search actually did something.
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

    setLoading(true);
    setError(null);
    try {
      const opportunities = await bestObservations({
        latitude_deg: location.latitudeDeg,
        longitude_deg: location.longitudeDeg,
        altitude_m: location.altitudeM,
        method: settings.method,
        norad_ids: satellites.map((s) => s.noradId),
        within_hours: settings.withinHours,
        min_elevation_deg: settings.minElevationDeg,
        min_score: 0,
        limit: MAX_RESULTS,
      });
      setResults(opportunities);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not find observation opportunities.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  function selectOpportunity(opportunity: RankedOpportunity): void {
    setSelected(opportunity);
    // Freeze the location used for this dossier so that further edits to
    // the location form (which the person can still see and use) don't
    // retroactively change the pass that's already open.
    setSelectedLocation(location);
  }

  return (
    <div className="mission-control">
      <div className="mission-control__controls">
        <LocationForm location={location} onChange={setLocation} />
        <SatellitePicker satellites={satellites} onChange={setSatellites} />
        <ObservationControls settings={settings} onChange={setSettings} />
      </div>

      <div className="mission-control__actions">
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => void findBestOpportunities()}
          disabled={loading}
        >
          {loading ? "Searching..." : "Find best opportunities"}
        </button>
        {error && <p className="error-text">{error}</p>}
      </div>

      <div className="mission-control__results" ref={resultsRef}>
        <div className="mission-control__queue">
          <h2 className="section-title">Mission queue</h2>
          {results === null && !loading && (
            <p className="help-text">
              Set your location and satellites, then search to see every qualifying pass here.
            </p>
          )}
          {results !== null && (
            <RankedOpportunityList
              opportunities={results}
              selectedKey={selected ? opportunityKey(selected) : null}
              onSelect={selectOpportunity}
            />
          )}
        </div>

        <div className="mission-control__dossier">
          {selected && selectedLocation ? (
            <PassDossier
              key={opportunityKey(selected)}
              opportunity={selected}
              location={selectedLocation}
              onClose={() => setSelected(null)}
            />
          ) : (
            <div className="card mission-control__dossier-placeholder">
              <p className="help-text">
                Select a pass from the mission queue to view its dossier: rise/peak/set timeline,
                sky path, 3D view, and the observation-suitability breakdown.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
