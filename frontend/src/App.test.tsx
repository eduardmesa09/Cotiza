import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("muestra la API como disponible cuando /api/health responde", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(screen.getByRole("heading", { name: "COTIZA+" })).toBeInTheDocument();
    expect(await screen.findByText("disponible")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/health");
  });

  it("muestra la API como no disponible cuando la consulta falla", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("sin conexión")));

    render(<App />);

    expect(await screen.findByText("no disponible")).toBeInTheDocument();
  });
});
