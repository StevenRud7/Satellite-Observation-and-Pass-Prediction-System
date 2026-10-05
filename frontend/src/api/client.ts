/**
 * API client.
 *
 * All backend calls go through here rather than scattering fetch() calls
 * across components - this keeps the base URL, error handling, and
 * request/response shapes in one place.
 */
import type {
  GeocodeResult,
  MethodVisibility,
  ObservationMethod,
  ObserverLocation,
  ObserverResponse,
  PassWithVisibility,
  RankedOpportunity,
  SatelliteRecord,
  SatelliteSearchResult,
} from "../types/api";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface HealthResponse {
  status: string;
  service: string;
  timestamp: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Could not reach the backend. Is it running?");
  }

  if (!response.ok) {
    // The backend returns {"detail": "..."} for errors (FastAPI's default
    // shape, matched by our own handlers too) - surface that when present.
    let detail: string | undefined;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail;
    } catch {
      // Response wasn't JSON - fall back to the generic message below.
    }
    throw new ApiError(detail ?? `Backend returned an error (${response.status})`, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function toQueryString(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params as Record<string, unknown>)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) {
      value.forEach((v) => search.append(key, String(v)));
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export async function fetchSatellite(noradId: number): Promise<SatelliteRecord> {
  return request<SatelliteRecord>(`/api/satellites/${noradId}`);
}

export async function fetchSatelliteCatalog(): Promise<SatelliteSearchResult[]> {
  return request<SatelliteSearchResult[]>("/api/satellites/catalog");
}

export async function searchSatellites(query: string): Promise<SatelliteSearchResult[]> {
  return request<SatelliteSearchResult[]>(`/api/satellites/search${toQueryString({ q: query })}`);
}

export async function geocode(query: string): Promise<GeocodeResult[]> {
  return request<GeocodeResult[]>(`/api/geocode${toQueryString({ q: query })}`);
}

export async function createObserver(location: ObserverLocation): Promise<ObserverResponse> {
  return request<ObserverResponse>("/api/observers", {
    method: "POST",
    body: JSON.stringify(location),
  });
}

export async function listObservers(): Promise<ObserverResponse[]> {
  return request<ObserverResponse[]>("/api/observers");
}

export interface PredictPassesParams {
  norad_id: number;
  observer_id?: number;
  latitude_deg?: number;
  longitude_deg?: number;
  altitude_m?: number;
  observer_name?: string;
  start: string;
  end: string;
  min_elevation_deg?: number;
}

export async function predictPasses(params: PredictPassesParams): Promise<PassWithVisibility[]> {
  return request<PassWithVisibility[]>("/api/passes/predict", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getPassVisibility(passId: number): Promise<MethodVisibility[]> {
  return request<MethodVisibility[]>(`/api/passes/${passId}/visibility`);
}

export interface BestObservationsParams {
  latitude_deg: number;
  longitude_deg: number;
  altitude_m?: number;
  method: ObservationMethod;
  norad_ids: number[];
  within_hours?: number;
  min_elevation_deg?: number;
  min_score?: number;
  limit?: number;
}

export async function bestObservations(
  params: BestObservationsParams,
): Promise<RankedOpportunity[]> {
  return request<RankedOpportunity[]>(`/api/observations/best${toQueryString(params)}`);
}
