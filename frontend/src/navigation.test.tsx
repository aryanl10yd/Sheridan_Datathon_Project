// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PrimaryNavigation } from "./PrimaryNavigation";

describe("PrimaryNavigation", () => {
  afterEach(cleanup);

  it("renders four destinations and marks the active section", () => {
    render(<PrimaryNavigation activeSection="historical" onSelect={vi.fn()} />);
    expect(screen.getAllByRole("button")).toHaveLength(4);
    expect(screen.getByRole("button", { name: "Historical Activity" })).toHaveAttribute("aria-current", "page");
  });

  it("selects a section without reloading", () => {
    const onSelect = vi.fn();
    render(<PrimaryNavigation activeSection="historical" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: "Mission Control" }));
    expect(onSelect).toHaveBeenCalledWith("mission");
  });
});
