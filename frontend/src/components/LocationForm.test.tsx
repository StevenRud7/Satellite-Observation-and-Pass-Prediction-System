import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LocationForm, { type Location } from "./LocationForm";

const DEFAULT_LOCATION: Location = {
  name: null,
  latitudeDeg: 0,
  longitudeDeg: 0,
  altitudeM: 0,
  observerId: null,
};

function mockFetchByUrl(handlers: Record<string, () => Promise<unknown>>) {
  return vi.fn((url: string) => {
    const match = Object.keys(handlers).find((pattern) => url.includes(pattern));
    if (!match) return Promise.reject(new Error(`Unhandled fetch: ${url}`));
    return handlers[match]().then((body) => ({ ok: true, status: 200, json: async () => body }));
  });
}

describe("LocationForm", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("lets a person search for a place and fills in coordinates on selection", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetchByUrl({
        "/api/observers": async () => [],
        "/api/geocode": async () => [
          {
            display_name: "Tel Aviv-Yafo, Tel Aviv District, Israel",
            latitude_deg: 32.0853,
            longitude_deg: 34.7818,
            place_type: "city",
            country: "Israel",
          },
        ],
      }),
    );

    const onChange = vi.fn();
    render(<LocationForm location={DEFAULT_LOCATION} onChange={onChange} />);

    fireEvent.change(screen.getByLabelText(/search a city or district/i), {
      target: { value: "Tel Aviv" },
    });

    await waitFor(
      () =>
        expect(screen.getByText(/Tel Aviv-Yafo, Tel Aviv District, Israel/)).toBeInTheDocument(),
      { timeout: 2000 },
    );

    fireEvent.click(screen.getByText(/Tel Aviv-Yafo, Tel Aviv District, Israel/));

    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ latitudeDeg: 32.0853, longitudeDeg: 34.7818 }),
    );
  });

  it("shows an error message when the place search fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("/api/observers")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => [] });
        }
        return Promise.resolve({
          ok: false,
          status: 502,
          json: async () => ({ detail: "Place search unavailable" }),
        });
      }),
    );

    render(<LocationForm location={DEFAULT_LOCATION} onChange={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/search a city or district/i), {
      target: { value: "Somewhere" },
    });

    await waitFor(() => expect(screen.getByText("Place search unavailable")).toBeInTheDocument(), {
      timeout: 2000,
    });
  });
});
