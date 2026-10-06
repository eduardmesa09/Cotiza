// Cliente de la API. Adjunta el token, traduce los errores a mensajes legibles y avisa
// cuando la sesión deja de ser válida.

const TOKEN_KEY = "cotiza.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let onUnauthorized: () => void = () => {};

export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

/** FastAPI devuelve `detail` como texto (errores de negocio) o como lista (validación). */
function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] };
    const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
    return `Dato inválido${field ? ` en «${field}»` : ""}: ${first.msg ?? "revise el formulario"}`;
  }
  if (status >= 500) return "El servidor no pudo completar la operación. Intente de nuevo.";
  return "No se pudo completar la operación.";
}

async function request(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "No hay conexión con el servidor.");
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    // Un 401 fuera del login significa que el token venció o el usuario fue desactivado.
    if (response.status === 401 && path !== "/auth/login") onUnauthorized();
    throw new ApiError(response.status, errorMessage(payload, response.status));
  }
  return response;
}

async function json<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await request(method, path, body);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  get: <T>(path: string) => json<T>("GET", path),
  post: <T>(path: string, body?: unknown) => json<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => json<T>("PUT", path, body),
  delete: (path: string) => json<void>("DELETE", path),

  /** Descarga un archivo protegido (el PDF) y lo entrega al navegador con su nombre. */
  async download(path: string, fallbackName: string): Promise<void> {
    const response = await request("GET", path);
    const match = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") ?? "");
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = match?.[1] ?? fallbackName;
    link.click();
    URL.revokeObjectURL(url);
  },
};
