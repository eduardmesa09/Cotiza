import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { assess, KpiCard } from "../pages/Dashboard";
import { promotionStatus } from "../pages/Pricing";
import { kpi, line } from "../test/helpers";
import { lineAlerts, LinesTable, type ViewLine } from "./LinesTable";

const view = (overrides = {}, input: Partial<ViewLine> = {}): ViewLine => {
  const result = line(overrides);
  return { referencia: result.referencia, descripcion: result.descripcion ?? "", cantidad: String(result.cantidad), adicional: "0", result, ...input };
};

describe("alertas de una línea", () => {
  it("una línea normal no tiene alertas", () => {
    expect(lineAlerts(line())).toEqual([]);
  });

  it("bajo pedido es una advertencia que no bloquea", () => {
    expect(lineAlerts(line({ bajo_pedido: true }))).toEqual([{ key: "bajo-pedido", label: "Bajo pedido", tone: "warn" }]);
  });

  it("margen bajo el mínimo pide aprobación", () => {
    expect(lineAlerts(line({ requiere_aprobacion: true })).map((a) => a.label)).toEqual(["Requiere aprobación"]);
  });

  it("bajo costo es un bloqueo y no se presenta como aprobable", () => {
    const alerts = lineAlerts(line({ estado: "BAJO_COSTO", requiere_aprobacion: true }));
    expect(alerts).toEqual([{ key: "bajo-costo", label: "Bajo costo", tone: "bad" }]);
  });

  it("no cotizable y bajo pedido pueden coincidir", () => {
    expect(lineAlerts(line({ estado: "NO_COTIZABLE", bajo_pedido: true })).map((a) => a.label)).toEqual(["No cotizable", "Bajo pedido"]);
  });
});

describe("tabla de líneas", () => {
  it("muestra precio, margen con su mínimo, total y disponibilidad", () => {
    render(<LinesTable lines={[view()]} />);
    const row = screen.getByText("POR-DEMO01").closest("tr")!;
    expect(within(row).getByText("729,60")).toBeInTheDocument();
    expect(within(row).getByText("15,02 %")).toBeInTheDocument();
    expect(within(row).getByText("mín. 8 %")).toBeInTheDocument();
    expect(within(row).getByText("14.592,00")).toBeInTheDocument();
    expect(within(row).getByText(/150 u/)).toBeInTheDocument();
  });

  it("muestra las alertas de cada línea", () => {
    render(
      <LinesTable
        lines={[
          view({ referencia: "A-1", bajo_pedido: true }),
          view({ referencia: "B-2", requiere_aprobacion: true, margen: "0.0662" }),
          view({ referencia: "C-3", estado: "BAJO_COSTO", requiere_aprobacion: true, margen: "-0.0622" }),
        ]}
      />,
    );
    expect(within(screen.getByText("A-1").closest("tr")!).getByText("Bajo pedido")).toBeInTheDocument();
    expect(within(screen.getByText("B-2").closest("tr")!).getByText("Requiere aprobación")).toBeInTheDocument();
    const blocked = within(screen.getByText("C-3").closest("tr")!);
    expect(blocked.getByText("Bajo costo")).toBeInTheDocument();
    expect(blocked.queryByText("Requiere aprobación")).not.toBeInTheDocument();
  });

  it("despliega las reglas aplicadas con el precio que dejó cada una", async () => {
    render(<LinesTable lines={[view()]} />);
    expect(screen.queryByText("Reglas aplicadas")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /ver reglas aplicadas a POR-DEMO01/i }));
    expect(screen.getByText("Reglas aplicadas")).toBeInTheDocument();
    expect(screen.getByText("RN-02")).toBeInTheDocument();
    expect(screen.getByText("Descuento por nivel Plata (4 %)")).toBeInTheDocument();
    expect(screen.getByText("→ 768,00")).toBeInTheDocument();
  });

  it("en modo lectura no hay campos ni botón de quitar", () => {
    render(<LinesTable lines={[view()]} />);
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /quitar/i })).not.toBeInTheDocument();
  });

  it("en modo edición avisa los cambios de cantidad y descuento, y permite quitar la línea", async () => {
    const onChange = vi.fn();
    const onRemove = vi.fn();
    render(<LinesTable lines={[view()]} editable onChange={onChange} onRemove={onRemove} />);

    await userEvent.type(screen.getByLabelText("Cantidad de POR-DEMO01"), "5");
    expect(onChange).toHaveBeenLastCalledWith(0, { cantidad: "205" });
    await userEvent.type(screen.getByLabelText(/descuento adicional de POR-DEMO01/i), "9");
    expect(onChange).toHaveBeenLastCalledWith(0, { adicional: "9" });
    await userEvent.click(screen.getByRole("button", { name: "Quitar POR-DEMO01" }));
    expect(onRemove).toHaveBeenCalledWith(0);
  });

  it("una línea sin calcular muestra guiones en vez de precios", () => {
    render(<LinesTable lines={[{ referencia: "NUEVA-1", descripcion: "Recién agregada", cantidad: "1", adicional: "0" }]} editable />);
    const row = screen.getByText("NUEVA-1").closest("tr")!;
    expect(within(row).getAllByText("—").length).toBeGreaterThanOrEqual(4);
  });
});

describe("indicadores", () => {
  it("bajar un indicador de tiempo es una mejora", () => {
    const result = assess(kpi({ valor: 1.6, linea_base: 6.4, meta: 1.5, sentido: "menor" }));
    expect(result.changePct).toBeCloseTo(-75);
    expect([result.improved, result.meetsTarget]).toEqual([true, false]);
    expect(assess(kpi({ valor: 1.2, linea_base: 6.4, meta: 1.5, sentido: "menor" })).meetsTarget).toBe(true);
  });

  it("subir un indicador de cumplimiento es una mejora", () => {
    const result = assess(kpi({ valor: 95, linea_base: 58, meta: 92, sentido: "mayor", unidad: "%" }));
    expect(result.improved).toBe(true);
    expect(result.meetsTarget).toBe(true);
    expect(assess(kpi({ valor: 40, linea_base: 58, meta: 92, sentido: "mayor" })).improved).toBe(false);
  });

  it("sin valor o sin línea base no se afirma mejora", () => {
    expect(assess(kpi({ valor: null }))).toEqual({ changePct: null, improved: null, meetsTarget: null });
    expect(assess(kpi({ valor: 100, linea_base: null, meta: 90, sentido: "mayor" }))).toEqual({ changePct: null, improved: null, meetsTarget: true });
  });

  it("un indicador de contexto, sin meta, muestra la variación pero no la califica", () => {
    const context = kpi({ codigo: "K10", valor: 33.3, linea_base: 22, meta: null, unidad: "%" });
    expect(assess(context)).toMatchObject({ improved: null, meetsTarget: null });
    render(<KpiCard kpi={context} />);
    expect(screen.getByText(/\+51 %/)).toBeInTheDocument();
    expect(screen.queryByText(/mejora|empeora|meta/)).not.toBeInTheDocument();
  });

  it("la tarjeta compara el valor medido con la línea base y la meta", () => {
    render(<KpiCard kpi={kpi()} />);
    expect(screen.getByRole("heading", { name: "Tiempo de respuesta al canal" })).toBeInTheDocument();
    expect(screen.getAllByText("1,6 h").length).toBeGreaterThan(0);
    expect(screen.getByText("6,4 h")).toBeInTheDocument();
    expect(screen.getByText(/−75 %/)).toBeInTheDocument();
    expect(screen.getByText(/mejora/)).toBeInTheDocument();
    expect(screen.getByText(/Aún no cumple la meta \(1,5 h\)/)).toBeInTheDocument();
    expect(screen.getByText(/12 casos/)).toBeInTheDocument();
  });

  it("la tarjeta sin datos lo dice en lugar de mostrar un cero", () => {
    render(<KpiCard kpi={kpi({ valor: null, muestra: 0 })} />);
    expect(screen.getByText("Sin datos todavía")).toBeInTheDocument();
    expect(screen.getByText(/Sin casos aún/)).toBeInTheDocument();
    expect(screen.queryByText(/mejora|empeora/)).not.toBeInTheDocument();
  });
});

describe("estado de una promoción", () => {
  const promo = { fecha_inicio: "2026-10-01", fecha_fin: "2026-10-31" };
  it("vigente con los dos extremos incluidos", () => {
    expect(promotionStatus(promo, "2026-10-01")).toBe("vigente");
    expect(promotionStatus(promo, "2026-10-31")).toBe("vigente");
  });
  it("vencida y futura", () => {
    expect(promotionStatus(promo, "2026-11-01")).toBe("vencida");
    expect(promotionStatus(promo, "2026-09-30")).toBe("futura");
  });
});
