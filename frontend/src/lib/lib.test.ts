import { describe, expect, it } from "vitest";
import { quote, userOf } from "../test/helpers";
import {
  formatDate,
  formatDuration,
  formatKpi,
  formatMoney,
  formatPercent,
  fractionToPercentInput,
  percentInputToFraction,
  toLocalInput,
} from "./format";
import { canAccess, homeFor, navFor, quoteActions } from "./permissions";
import type { Role } from "./types";

// El espacio que usa Intl puede ser de no separación: se normaliza para comparar.
const plain = (text: string) => text.replace(/\s/g, " ");

describe("formato", () => {
  it("muestra el dinero con separadores de Colombia", () => {
    expect(plain(formatMoney("14592.5"))).toBe("USD 14.592,50");
    expect(plain(formatMoney("729.60", false))).toBe("729,60");
    expect(formatMoney(null)).toBe("—");
  });

  it("convierte fracciones a porcentaje sin decimales sobrantes", () => {
    expect(formatPercent("0.1502")).toBe("15,02 %");
    expect(formatPercent("0.0400")).toBe("4 %");
    expect(formatPercent("0.0250")).toBe("2,5 %");
    expect(formatPercent(null)).toBe("—");
  });

  it("va y vuelve entre el campo de porcentaje y la fracción de la API", () => {
    expect(fractionToPercentInput("0.0900")).toBe("9");
    expect(fractionToPercentInput("0.0250")).toBe("2.5");
    expect(percentInputToFraction("9")).toBe("0.0900");
    expect(percentInputToFraction("2,5")).toBe("0.0250");
    expect(percentInputToFraction("")).toBe("0.0000");
    expect(percentInputToFraction("abc")).toBe("0");
  });

  it("resume duraciones", () => {
    expect(formatDuration(59)).toBe("59 s");
    expect(formatDuration(45 * 60)).toBe("45 min");
    expect(formatDuration(3600)).toBe("1 h");
    expect(formatDuration(5400)).toBe("1 h 30 min");
    expect(formatDuration(-5)).toBe("0 s");
  });

  it("muestra indicadores con su unidad", () => {
    expect(formatKpi(7.67, "min")).toBe("7,7 min");
    expect(formatKpi(92, "%")).toBe("92 %");
    expect(formatKpi(null, "h")).toBe("—");
  });

  it("muestra fechas sin correrlas de día y arma el valor de un campo de fecha y hora", () => {
    expect(formatDate("2026-11-04")).toContain("4");
    expect(formatDate("2026-11-04")).toContain("nov");
    expect(toLocalInput(new Date(2026, 9, 5, 9, 7))).toBe("2026-10-05T09:07");
  });
});

describe("navegación por rol", () => {
  it("cada rol empieza en su pantalla principal", () => {
    expect(homeFor("ejecutivo")).toBe("/cotizaciones");
    expect(homeFor("aprobador")).toBe("/aprobaciones");
    expect(homeFor("gerente")).toBe("/tablero");
    expect(homeFor("pricing")).toBe("/pricing");
    expect(homeFor("admin")).toBe("/usuarios");
  });

  it("el menú refleja la matriz de permisos", () => {
    const routes = (rol: Role) => navFor(rol).map((item) => item.to);
    expect(routes("ejecutivo")).toEqual(["/cotizaciones", "/seguimiento", "/tablero"]);
    expect(routes("admin")).toEqual(["/usuarios", "/parametros"]);
    expect(routes("pricing")).toContain("/pricing");
    expect(routes("aprobador")).not.toContain("/pricing");
  });

  it("solo el ejecutivo crea cotizaciones; los demás las consultan", () => {
    expect(canAccess("ejecutivo", "/cotizaciones/nueva")).toBe(true);
    expect(canAccess("aprobador", "/cotizaciones/nueva")).toBe(false);
    expect(canAccess("aprobador", "/cotizaciones/12")).toBe(true);
    expect(canAccess("admin", "/cotizaciones/12")).toBe(false);
    expect(canAccess("admin", "/tablero")).toBe(false);
    expect(canAccess("ejecutivo", "/aprobaciones")).toBe(false);
    expect(canAccess("ejecutivo", "/usuarios")).toBe(false);
  });
});

describe("acciones sobre una cotización", () => {
  const owner = userOf("ejecutivo", 1);

  it("el dueño puede emitir una cotización lista y con el cálculo al día", () => {
    const actions = quoteActions(quote(), owner);
    expect(actions.issue).toBe(true);
    expect(actions.edit).toBe(true);
    expect(actions.requestApproval).toBe(false);
  });

  it("con cambios sin calcular no se puede emitir ni solicitar aprobación", () => {
    expect(quoteActions(quote(), owner, true).issue).toBe(false);
    const needsApproval = quote({ evaluacion: "REQUIERE_APROBACION", acciones_permitidas: ["CALCULAR", "EDITAR", "SOLICITAR_APROBACION"] });
    expect(quoteActions(needsApproval, owner, false).requestApproval).toBe(true);
    expect(quoteActions(needsApproval, owner, true).requestApproval).toBe(false);
  });

  it("si requiere aprobación o no es emitible, emitir queda deshabilitado", () => {
    const needsApproval = quote({ evaluacion: "REQUIERE_APROBACION", acciones_permitidas: ["CALCULAR", "EDITAR", "SOLICITAR_APROBACION"] });
    const notIssuable = quote({ evaluacion: "NO_EMITIBLE", acciones_permitidas: ["CALCULAR", "EDITAR"] });
    expect(quoteActions(needsApproval, owner).issue).toBe(false);
    expect(quoteActions(notIssuable, owner).issue).toBe(false);
    expect(quoteActions(notIssuable, owner).requestApproval).toBe(false);
  });

  it("pendiente de aprobación: solo se emite una vez aprobada", () => {
    const pending = quote({ estado: "PENDIENTE_APROBACION", acciones_permitidas: ["APROBAR", "ESCALAR", "RECHAZAR"] });
    const approved = quote({ estado: "PENDIENTE_APROBACION", acciones_permitidas: ["EMITIR"] });
    expect(quoteActions(pending, owner).issue).toBe(false);
    expect(quoteActions(pending, owner).edit).toBe(false);
    expect(quoteActions(approved, owner).issue).toBe(true);
  });

  it("otro ejecutivo y los demás roles no pueden actuar, pero sí descargar el PDF", () => {
    const issued = quote({ estado: "EMITIDA", acciones_permitidas: ["GANAR", "INICIAR_SEGUIMIENTO", "VENCER"], puede_crear_version: true, tiene_pdf: true });
    for (const user of [userOf("ejecutivo", 99), userOf("aprobador", 2), userOf("gerente", 3), userOf("pricing", 4)]) {
      const actions = quoteActions(issued, user);
      expect([actions.edit, actions.issue, actions.win, actions.lose, actions.newVersion]).toEqual([false, false, false, false, false]);
      expect(actions.downloadPdf).toBe(true);
    }
  });

  it("emitida: se puede ganar y versionar; perder solo desde seguimiento", () => {
    const issued = quote({ estado: "EMITIDA", acciones_permitidas: ["GANAR", "INICIAR_SEGUIMIENTO", "VENCER"], puede_crear_version: true });
    const following = quote({ estado: "EN_SEGUIMIENTO", acciones_permitidas: ["GANAR", "PERDER", "VENCER"], puede_crear_version: true });
    expect(quoteActions(issued, owner)).toMatchObject({ win: true, lose: false, newVersion: true, edit: false, issue: false });
    expect(quoteActions(following, owner)).toMatchObject({ win: true, lose: true });
  });

  it("una versión reemplazada no admite acciones", () => {
    const replaced = quote({ estado: "EMITIDA", reemplazada: true, acciones_permitidas: [], puede_crear_version: false, tiene_pdf: true });
    expect(quoteActions(replaced, owner)).toMatchObject({ win: false, newVersion: false, downloadPdf: true });
  });
});
