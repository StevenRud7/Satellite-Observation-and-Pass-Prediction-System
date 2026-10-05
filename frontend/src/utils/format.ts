import type { RankedOpportunity, VisibilityClassification } from "../types/api";

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs.toString().padStart(2, "0")}s`;
}

export function formatDegrees(value: number): string {
  return `${Math.round(value)}°`;
}

const CLASSIFICATION_LABEL: Record<VisibilityClassification, string> = {
  excellent: "Excellent",
  very_good: "Very Good",
  possible: "Possible",
  difficult: "Difficult",
  unlikely: "Unlikely",
};

const CLASSIFICATION_COLOR_VAR: Record<VisibilityClassification, string> = {
  excellent: "--color-excellent",
  very_good: "--color-very-good",
  possible: "--color-possible",
  difficult: "--color-difficult",
  unlikely: "--color-unlikely",
};

export function classificationLabel(classification: VisibilityClassification): string {
  return CLASSIFICATION_LABEL[classification];
}

export function classificationColorVar(classification: VisibilityClassification): string {
  return `var(${CLASSIFICATION_COLOR_VAR[classification]})`;
}

const METHOD_LABEL: Record<string, string> = {
  naked_eye: "Naked Eye",
  binoculars: "Binoculars",
  telescope: "Telescope",
};

export function methodLabel(method: string): string {
  return METHOD_LABEL[method] ?? method;
}

/** Stable identity for a ranked opportunity (a satellite + a specific pass),
 * used to track which mission-queue row is selected/open in the dossier. */
export function opportunityKey(opportunity: RankedOpportunity): string {
  return `${opportunity.norad_id}-${opportunity.pass_event.rise_time}`;
}
