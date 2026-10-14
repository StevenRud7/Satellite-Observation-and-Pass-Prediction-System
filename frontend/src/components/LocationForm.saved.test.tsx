import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LocationForm, { type Location } from "./LocationForm";

const LOCATION: Location = {
  name: "Home",
  latitudeDeg: 40.7,
  longitudeDeg: -74,
  altitudeM: 10,
  observerId: null,
};

function mockApi(saved: unknown[], created: unknown) {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      const body = method === "POST" ? created : url.includes("/api/observers") ? saved : [];
      return new Response(JSON.stringify(body), {
        status: method === "POST" ? 201 : 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("LocationForm saved locations", () => {
  it("does not save anything until the Save button is clicked", async () => {
    const calls = mockApi([], {
      id: 7,
      name: "Home",
      latitude_deg: 40.7,
      longitude_deg: -74,
      altitude_m: 10,
    });
    render(<LocationForm location={LOCATION} onChange={() => {}} />);

    // Editing fields must not create saved locations.
    fireEvent.change(screen.getByLabelText(/latitude/i), { target: { value: "41" } });
    await waitFor(() => expect(calls.some((c) => c.method === "GET")).toBe(true));
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: /save this location/i }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(1));
  });

  it("shows a place only once even if the backend returns an already-listed entry", async () => {
    const existing = {
      id: 7,
      name: "Home",
      latitude_deg: 40.7,
      longitude_deg: -74,
      altitude_m: 10,
    };
    mockApi([existing], existing);
    render(<LocationForm location={LOCATION} onChange={() => {}} />);

    await screen.findByRole("option", { name: "Home" });
    fireEvent.click(screen.getByRole("button", { name: /save this location/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save this location/i })).toBeEnabled(),
    );
    expect(screen.getAllByRole("option", { name: "Home" })).toHaveLength(1);
  });

  it("disables the button and reads 'Saved' when the current location is already a saved one", () => {
    mockApi([], {});
    render(<LocationForm location={{ ...LOCATION, observerId: 7 }} onChange={() => {}} />);
    expect(screen.getByRole("button", { name: "Saved" })).toBeDisabled();
  });
});
