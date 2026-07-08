import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { demoWorkbench } from "./workbench";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllEnvs();
});

describe("App", () => {
  it("renders every M1 queue section from the workbench read model", async () => {
    vi.stubEnv("VITE_KAIROTA_API_BASE_URL", "https://api.example.test");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => demoWorkbench,
    });

    render(<App />);

    for (const title of ["Ready", "Running", "Blocked", "Waiting", "Failed", "Done"]) {
      expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByRole("heading", { name: "Decision Inbox" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent Events" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Failures" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/queue/workbench",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByText(/Local API/)).toBeInTheDocument();
  });

  it("selects rows and updates the detail panel", async () => {
    vi.stubEnv("VITE_KAIROTA_API_BASE_URL", "https://api.example.test");
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => demoWorkbench,
    });

    render(<App />);

    await screen.findByRole("heading", { name: "Failed" });
    fireEvent.click(
      screen.getAllByRole("button", { name: /repair stale check reducer/i })[0],
    );

    const detail = screen.getByLabelText("Selected work item");
    expect(
      within(detail).getByRole("heading", { name: "Repair stale check reducer" }),
    ).toBeInTheDocument();
    expect(within(detail).getByText("blocked_by_ci")).toBeInTheDocument();
    expect(within(detail).getByText(/1 failing/)).toBeInTheDocument();
  });

  it("falls back to local demo data when the API is unavailable", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network down"));

    render(<App />);

    expect(await screen.findByText(/API unavailable/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Demo data/)).toBeInTheDocument();
    });
    expect(
      screen.getAllByText("Add queue workbench browser smoke")[0],
    ).toBeInTheDocument();
  });
});
