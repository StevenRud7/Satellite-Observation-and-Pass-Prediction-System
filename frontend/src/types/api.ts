// Mirrors backend Pydantic schemas (app/schemas/*). Kept as plain
// interfaces, no runtime validation - the backend is the source of truth
// for correctness; these just give us autocomplete and type-checking.

export interface OrbitalElementSet {
  epoch: string;
  line1: string;
  line2: string;
  mean_motion: number;
  eccentricity: number;
  inclination_deg: number;
  raan_deg: number;
  arg_perigee_deg: number;
  mean_anomaly_deg: number;
  bstar: number;
  element_set_number: number;
  revolution_number: number;
  source: string;
  retrieved_at: string;
}

export interface SatelliteRecord {
  norad_id: number;
  name: string;
  international_designator: string | null;
  object_type: string | null;
  orbital_elements: OrbitalElementSet;
}

export interface ObserverLocation {
  name: string | null;
  latitude_deg: number;
  longitude_deg: number;
  altitude_m: number;
}

export interface ObserverResponse extends ObserverLocation {
  id: number;
}

export interface SatelliteSearchResult {
  norad_id: number;
  name: string;
  category: string | null;
}

export interface GeocodeResult {
  display_name: string;
  latitude_deg: number;
  longitude_deg: number;
  place_type: string | null;
  country: string | null;
}

export interface PassEvent {
  rise_time: string;
  peak_time: string;
  set_time: string;
  rise_azimuth_deg: number;
  peak_azimuth_deg: number;
  set_azimuth_deg: number;
  max_elevation_deg: number;
  duration_seconds: number;
  rise_range_km: number;
  max_range_km: number;
  set_range_km: number;
  min_elevation_threshold_deg: number;
}

export type ObservationMethod = "naked_eye" | "binoculars" | "telescope";

export type VisibilityClassification =
  "excellent" | "very_good" | "possible" | "difficult" | "unlikely";

export type ConfidenceLevel = "high" | "medium" | "low";

export interface VisibilityFactor {
  label: string;
  detail: string;
}

export interface MethodVisibility {
  method: ObservationMethod;
  score: number;
  classification: VisibilityClassification;
  confidence: ConfidenceLevel;
  factors: VisibilityFactor[];
  limitations: string[];
}

export interface PassWithVisibility {
  id: number | null;
  norad_id: number;
  satellite_name: string;
  observer_id: number | null;
  pass_event: PassEvent;
  visibility: MethodVisibility[];
}

export interface RankedOpportunity {
  norad_id: number;
  satellite_name: string;
  pass_event: PassEvent;
  visibility: MethodVisibility;
}
