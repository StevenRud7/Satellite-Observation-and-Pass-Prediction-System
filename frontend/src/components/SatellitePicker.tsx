import { useEffect, useMemo, useState } from "react";

import { ApiError, fetchSatellite, fetchSatelliteCatalog, searchSatellites } from "../api/client";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type { SatelliteSearchResult } from "../types/api";

export interface TrackedSatellite {
  noradId: number;
  name: string;
}

interface SatellitePickerProps {
  satellites: TrackedSatellite[];
  onChange: (satellites: TrackedSatellite[]) => void;
}

function SatellitePicker({ satellites, onChange }: SatellitePickerProps) {
  const [catalog, setCatalog] = useState<SatelliteSearchResult[]>([]);

  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 350);
  const [searchResults, setSearchResults] = useState<SatelliteSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [resultsOpen, setResultsOpen] = useState(false);
  const [pickerError, setPickerError] = useState<string | null>(null);
  const [addingNoradId, setAddingNoradId] = useState<number | null>(null);

  const trackedIds = useMemo(() => new Set(satellites.map((s) => s.noradId)), [satellites]);

  useEffect(() => {
    fetchSatelliteCatalog()
      .then(setCatalog)
      .catch(() => {
        // The catalog is a browsing convenience; if it can't be loaded,
        // search-by-name and direct NORAD ID entry still work.
      });
  }, []);

  useEffect(() => {
    const trimmed = debouncedQuery.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      return;
    }

    let cancelled = false;
    setSearching(true);
    setPickerError(null);

    searchSatellites(trimmed)
      .then((results) => {
        if (!cancelled) setSearchResults(results);
      })
      .catch((error) => {
        if (!cancelled) {
          setSearchResults([]);
          setPickerError(
            error instanceof ApiError ? error.message : "Could not search for that satellite.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setSearching(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedQuery]);

  function addTracked(satellite: TrackedSatellite): void {
    if (trackedIds.has(satellite.noradId)) {
      setPickerError("That satellite is already in the list.");
      return;
    }
    onChange([...satellites, satellite]);
    setQuery("");
    setSearchResults([]);
    setResultsOpen(false);
    setPickerError(null);
  }

  async function addByNoradId(rawInput: string): Promise<void> {
    const noradId = Number(rawInput);
    if (!Number.isInteger(noradId) || noradId <= 0) {
      setPickerError("Enter a valid NORAD catalog ID, or search by name above.");
      return;
    }
    if (trackedIds.has(noradId)) {
      setPickerError("That satellite is already in the list.");
      return;
    }

    setAddingNoradId(noradId);
    setPickerError(null);
    try {
      const satellite = await fetchSatellite(noradId);
      addTracked({ noradId, name: satellite.name });
    } catch (error) {
      setPickerError(
        error instanceof ApiError ? error.message : "Could not look up that satellite.",
      );
    } finally {
      setAddingNoradId(null);
    }
  }

  function removeSatellite(noradId: number): void {
    onChange(satellites.filter((s) => s.noradId !== noradId));
  }

  const catalogByCategory = useMemo(() => {
    const groups = new Map<string, SatelliteSearchResult[]>();
    for (const entry of catalog) {
      const key = entry.category ?? "Other";
      const group = groups.get(key) ?? [];
      group.push(entry);
      groups.set(key, group);
    }
    return groups;
  }, [catalog]);

  const trimmedQuery = query.trim();
  const isNumericQuery = trimmedQuery.length > 0 && /^\d+$/.test(trimmedQuery);

  return (
    <div className="card">
      <h2 className="section-title">Satellites to consider</h2>

      <div className="satellite-list">
        {satellites.map((s) => (
          <div className="satellite-list__item" key={s.noradId}>
            <span>
              {s.name} <span className="satellite-list__id readout">#{s.noradId}</span>
            </span>
            <button
              type="button"
              className="btn btn--ghost"
              aria-label={`Remove ${s.name}`}
              onClick={() => removeSatellite(s.noradId)}
            >
              Remove
            </button>
          </div>
        ))}
        {satellites.length === 0 && <p className="help-text">No satellites added yet.</p>}
      </div>

      <div className="field" style={{ position: "relative" }}>
        <label className="field__label" htmlFor="satellite-search">
          Search by name or NORAD ID
        </label>
        <div className="satellite-list__add">
          <input
            id="satellite-search"
            className="field__input"
            type="text"
            placeholder="e.g. Hubble  or  25544"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setResultsOpen(true);
            }}
            onFocus={() => setResultsOpen(true)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && isNumericQuery && searchResults.length === 0) {
                void addByNoradId(trimmedQuery);
              }
            }}
            role="combobox"
            aria-expanded={resultsOpen && searchResults.length > 0}
            aria-controls="satellite-search-results"
            autoComplete="off"
          />
          {isNumericQuery && searchResults.length === 0 && (
            <button
              type="button"
              className="btn"
              onClick={() => void addByNoradId(trimmedQuery)}
              disabled={addingNoradId !== null}
            >
              {addingNoradId !== null ? "Looking up..." : "Add ID"}
            </button>
          )}
        </div>
        {searching && <p className="help-text">Searching CelesTrak...</p>}
        {resultsOpen && searchResults.length > 0 && (
          <ul id="satellite-search-results" className="place-results" role="listbox">
            {searchResults.map((result) => (
              <li key={result.norad_id}>
                <button
                  type="button"
                  className="place-results__option"
                  role="option"
                  aria-selected="false"
                  disabled={trackedIds.has(result.norad_id)}
                  onClick={() => addTracked({ noradId: result.norad_id, name: result.name })}
                >
                  <span className="place-results__name">{result.name}</span>
                  <span className="place-results__type readout">#{result.norad_id}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {pickerError && <p className="error-text">{pickerError}</p>}

      {catalogByCategory.size > 0 && (
        <div className="satellite-catalog">
          <p className="help-text">Or pick from well-known satellites:</p>
          {Array.from(catalogByCategory.entries()).map(([category, entries]) => (
            <div key={category} className="satellite-catalog__group">
              <span className="satellite-catalog__category label-caps">{category}</span>
              <div className="satellite-catalog__chips">
                {entries.map((entry) => (
                  <button
                    key={entry.norad_id}
                    type="button"
                    className="chip"
                    disabled={trackedIds.has(entry.norad_id)}
                    onClick={() => addTracked({ noradId: entry.norad_id, name: entry.name })}
                  >
                    {entry.name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default SatellitePicker;
