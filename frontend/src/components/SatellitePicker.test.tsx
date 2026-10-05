import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SatellitePicker, { type TrackedSatellite } from "./SatellitePicker";

function mockFetchByUrl(handlers: Record<string, () => Promise<unknown>>) {
  return vi.fn((url: string) => {
    const match = Object.keys(handlers).find((pattern) => url.includes(pattern));
    if (!match) return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    return handlers[match]().then((body) => ({ ok: true, status: 200, json: async () => body }));
  });
}

describe("SatellitePicker", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("shows curated catalog chips and adds a satellite when one is clicked", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/api/satellites/catalog": async () => [
          { norad_id: 20580, name: "HST (Hubble Space Telescope)", category: "Space Telescope" },
        ],
      }),
    );

    const onChange = vi.fn();
    render(<SatellitePicker satellites={[]} onChange={onChange} />);

    await waitFor(() =>
      expect(screen.getByText("HST (Hubble Space Telescope)")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByText("HST (Hubble Space Telescope)"));

    expect(onChange).toHaveBeenCalledWith([
      { noradId: 20580, name: "HST (Hubble Space Telescope)" },
    ]);
  });

  it("searches by name and adds the selected result", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/api/satellites/catalog": async () => [],
        "/api/satellites/search": async () => [{ norad_id: 25544, name: "ISS (ZARYA)" }],
      }),
    );

    const onChange = vi.fn();
    render(<SatellitePicker satellites={[]} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/search by name or norad id/i), {
      target: { value: "ISS" },
    });

    await waitFor(() => expect(screen.getByText("ISS (ZARYA)")).toBeInTheDocument(), {
      timeout: 2000,
    });

    fireEvent.click(screen.getByText("ISS (ZARYA)"));

    expect(onChange).toHaveBeenCalledWith([{ noradId: 25544, name: "ISS (ZARYA)" }]);
  });

  it("adds directly by NORAD ID when a numeric query has no name matches", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/api/satellites/catalog": async () => [],
        "/api/satellites/search": async () => [],
        "/api/satellites/25544": async () => ({
          norad_id: 25544,
          name: "ISS (ZARYA)",
          international_designator: null,
          object_type: null,
          orbital_elements: {
            line1: "1 25544U",
            line2: "2 25544",
            epoch: "2025-01-01T00:00:00Z",
            source: "celestrak",
            retrieved_at: "2025-01-01T00:00:00Z",
          },
        }),
      }),
    );

    const onChange = vi.fn();
    render(<SatellitePicker satellites={[]} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/search by name or norad id/i), {
      target: { value: "25544" },
    });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add id/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /add id/i }));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith([{ noradId: 25544, name: "ISS (ZARYA)" }]),
    );
  });

  it("removes a tracked satellite", async () => {
    vi.stubGlobal("fetch", mockFetchByUrl({ "/api/satellites/catalog": async () => [] }));
    const tracked: TrackedSatellite[] = [{ noradId: 25544, name: "ISS (ZARYA)" }];
    const onChange = vi.fn();

    render(<SatellitePicker satellites={tracked} onChange={onChange} />);
    // Let the (empty) catalog fetch settle before unmounting/finishing, so
    // its state update doesn't land outside act().
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /remove iss/i }));

    expect(onChange).toHaveBeenCalledWith([]);
  });
});
