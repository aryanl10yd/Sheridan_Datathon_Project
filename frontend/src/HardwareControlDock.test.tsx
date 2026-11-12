// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { HardwareControlDock } from "./HardwareControlDock";

const disconnectedStatus = {
  device_id: null,
  model: "Raspberry Pi Zero W v1.1",
  connection: "disconnected",
  simulated: false,
  mode: "PHYSICAL DEVICE",
  last_heartbeat: null,
  leds: { green: false, amber: false, red: false, blue: false },
  safe_mode: "idle",
  latest_error: null,
};

describe("HardwareControlDock", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((path: string) => {
      if (path === "/api/hardware/status") return Promise.resolve(new Response(JSON.stringify(disconnectedStatus), { status: 200 }));
      if (path === "/api/events") return Promise.resolve(new Response(JSON.stringify({ events: [] }), { status: 200 }));
      return Promise.resolve(new Response("Hardware device is disconnected", { status: 503 }));
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("starts collapsed and remains available while expanded", async () => {
    render(<HardwareControlDock />);
    const header = screen.getByRole("button", { name: /Raspberry Pi/ });
    expect(header).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("PHYSICAL DEVICE")).toBeInTheDocument();
  });

  it("prevents commands while disconnected and reports the error", async () => {
    render(<HardwareControlDock />);
    fireEvent.click(screen.getByRole("button", { name: /Raspberry Pi/ }));
    const command = await screen.findByRole("button", { name: /RUN LED SELF-TEST/ });
    fireEvent.click(command);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Hardware device is disconnected"));
    expect(command).not.toBeDisabled();
  });
});
