import { describe, expect, it } from "vitest";

import { formatDate, formatDateAndTime, formatPassDates } from "./format";

// Built from local-time components so the assertions hold in any time zone
// the test runner happens to use.
function localIso(y: number, m: number, d: number, hh: number, mm: number): string {
  return new Date(y, m - 1, d, hh, mm).toISOString();
}

describe("pass date formatting", () => {
  it("shows a single date when a pass stays within one local day", () => {
    const rise = localIso(2026, 10, 14, 21, 5);
    const set = localIso(2026, 10, 14, 21, 11);
    expect(formatPassDates(rise, set)).toBe(formatDate(rise));
    expect(formatPassDates(rise, set)).not.toContain("\u2013");
  });

  it("shows both dates when a pass runs through local midnight", () => {
    const rise = localIso(2026, 10, 14, 23, 58);
    const set = localIso(2026, 10, 15, 0, 4);
    const text = formatPassDates(rise, set);
    expect(text).toBe(`${formatDate(rise)} \u2013 ${formatDate(set)}`);
    expect(formatDate(rise)).not.toBe(formatDate(set));
  });

  it("combines date and time", () => {
    const iso = localIso(2026, 10, 14, 21, 5);
    expect(formatDateAndTime(iso)).toContain(formatDate(iso));
    expect(formatDateAndTime(iso)).toContain("\u00b7");
  });
});
