import { useEffect, useState } from "react";

import { ApiError, createObserver, geocode, listObservers } from "../api/client";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { GeocodeResult, ObserverResponse } from "../types/api";

export interface Location {
  name: string | null;
  latitudeDeg: number;
  longitudeDeg: number;
  altitudeM: number;
  observerId: number | null;
}

interface LocationFormProps {
  location: Location;
  onChange: (location: Location) => void;
}

function LocationForm({ location, onChange }: LocationFormProps) {
  const [savedObservers, setSavedObservers] = useState<ObserverResponse[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Place search: type a city, a district/neighbourhood, or a landmark
  // instead of (or in addition to) entering coordinates by hand.
  const [placeQuery, setPlaceQuery] = useState("");
  const debouncedPlaceQuery = useDebouncedValue(placeQuery, 350);
  const [placeResults, setPlaceResults] = useState<GeocodeResult[]>([]);
  const [placeSearching, setPlaceSearching] = useState(false);
  const [placeError, setPlaceError] = useState<string | null>(null);
  const [placeResultsOpen, setPlaceResultsOpen] = useState(false);

  useEffect(() => {
    listObservers()
      .then(setSavedObservers)
      .catch(() => {
        // Saved-locations list is a convenience, not required - fail quietly
        // (e.g. no database configured on the backend) rather than blocking the form.
      });
  }, []);

  useEffect(() => {
    const query = debouncedPlaceQuery.trim();
    if (query.length < 2) {
      setPlaceResults([]);
      setPlaceError(null);
      return;
    }

    let cancelled = false;
    setPlaceSearching(true);
    setPlaceError(null);

    geocode(query)
      .then((results) => {
        if (!cancelled) setPlaceResults(results);
      })
      .catch((error) => {
        if (!cancelled) {
          setPlaceResults([]);
          setPlaceError(
            error instanceof ApiError ? error.message : "Could not search for that place.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setPlaceSearching(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedPlaceQuery]);

  function update(partial: Partial<Location>): void {
    onChange({ ...location, observerId: null, ...partial });
  }

  function selectSaved(id: string): void {
    if (id === "") {
      update({});
      return;
    }
    const observer = savedObservers.find((o) => o.id === Number(id));
    if (!observer) return;
    onChange({
      name: observer.name,
      latitudeDeg: observer.latitude_deg,
      longitudeDeg: observer.longitude_deg,
      altitudeM: observer.altitude_m,
      observerId: observer.id,
    });
  }

  function selectPlace(result: GeocodeResult): void {
    // A short label ("Tel Aviv-Yafo" rather than the full comma-separated
    // display name) reads better once it's just sitting in the "Label"
    // field - the full name is still shown in the results dropdown itself.
    const shortLabel = result.display_name.split(",")[0]?.trim() || result.display_name;
    onChange({
      name: shortLabel,
      latitudeDeg: result.latitude_deg,
      longitudeDeg: result.longitude_deg,
      // Place search has no elevation data; keep whatever altitude was
      // already set (defaults to 0) and let the person adjust it.
      altitudeM: location.altitudeM,
      observerId: null,
    });
    setPlaceQuery("");
    setPlaceResults([]);
    setPlaceResultsOpen(false);
  }

  async function saveLocation(): Promise<void> {
    setSaving(true);
    setSaveError(null);
    try {
      const created = await createObserver({
        name: location.name,
        latitude_deg: location.latitudeDeg,
        longitude_deg: location.longitudeDeg,
        altitude_m: location.altitudeM,
      });
      setSavedObservers((prev) => [...prev, created]);
      onChange({ ...location, observerId: created.id });
    } catch (error) {
      setSaveError(error instanceof ApiError ? error.message : "Could not save this location.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2 className="section-title">Your location</h2>

      <div className="field" style={{ position: "relative" }}>
        <label className="field__label" htmlFor="place-search">
          Search a city or district
        </label>
        <input
          id="place-search"
          className="field__input"
          type="text"
          placeholder="e.g. Marina Bay, Singapore  or  Rio de Janeiro"
          value={placeQuery}
          onChange={(e) => {
            setPlaceQuery(e.target.value);
            setPlaceResultsOpen(true);
          }}
          onFocus={() => setPlaceResultsOpen(true)}
          role="combobox"
          aria-expanded={placeResultsOpen && placeResults.length > 0}
          aria-controls="place-search-results"
          autoComplete="off"
        />
        {placeSearching && <p className="help-text">Searching...</p>}
        {placeError && <p className="error-text">{placeError}</p>}
        {placeResultsOpen && placeResults.length > 0 && (
          <ul id="place-search-results" className="place-results" role="listbox">
            {placeResults.map((result, index) => (
              <li key={`${result.latitude_deg},${result.longitude_deg},${index}`}>
                <button
                  type="button"
                  className="place-results__option"
                  role="option"
                  aria-selected="false"
                  onClick={() => selectPlace(result)}
                >
                  <span className="place-results__name">{result.display_name}</span>
                  {result.place_type && (
                    <span className="place-results__type">{result.place_type}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="help-text">
          Works for cities as well as smaller areas - neighbourhoods, districts, towns. Picking a
          result fills in the coordinates below, which you can still fine-tune by hand.
        </p>
      </div>

      {savedObservers.length > 0 && (
        <div className="field">
          <label className="field__label" htmlFor="saved-observer">
            Saved locations
          </label>
          <select
            id="saved-observer"
            className="field__select"
            value={location.observerId ?? ""}
            onChange={(e) => selectSaved(e.target.value)}
          >
            <option value="">Enter manually...</option>
            {savedObservers.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name ?? `${o.latitude_deg.toFixed(2)}, ${o.longitude_deg.toFixed(2)}`}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="field-row">
        <div className="field">
          <label className="field__label" htmlFor="latitude">
            Latitude
          </label>
          <input
            id="latitude"
            className="field__input"
            type="number"
            step="0.0001"
            min={-90}
            max={90}
            value={location.latitudeDeg}
            onChange={(e) => update({ latitudeDeg: Number(e.target.value) })}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="longitude">
            Longitude
          </label>
          <input
            id="longitude"
            className="field__input"
            type="number"
            step="0.0001"
            min={-180}
            max={180}
            value={location.longitudeDeg}
            onChange={(e) => update({ longitudeDeg: Number(e.target.value) })}
          />
        </div>
        <div className="field">
          <label className="field__label" htmlFor="altitude">
            Altitude (m)
          </label>
          <input
            id="altitude"
            className="field__input"
            type="number"
            step="1"
            value={location.altitudeM}
            onChange={(e) => update({ altitudeM: Number(e.target.value) })}
          />
        </div>
      </div>

      <div className="field">
        <label className="field__label" htmlFor="location-name">
          Label (optional)
        </label>
        <input
          id="location-name"
          className="field__input"
          type="text"
          placeholder="Home"
          value={location.name ?? ""}
          onChange={(e) => update({ name: e.target.value || null })}
        />
      </div>

      <button type="button" className="btn" onClick={() => void saveLocation()} disabled={saving}>
        {saving ? "Saving..." : "Save this location"}
      </button>
      {saveError && <p className="error-text">{saveError}</p>}
    </div>
  );
}

export default LocationForm;
