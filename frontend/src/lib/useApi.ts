import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

interface Result<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  /** Sustituye los datos sin volver a pedirlos (por ejemplo, con la respuesta de una acción). */
  setData: (data: T) => void;
}

/** Carga datos de la API. Con `refreshMs`, los vuelve a pedir periódicamente en segundo
 *  plano (colas y plazos que cambian solos). `path` nulo no pide nada. */
export function useApi<T>(path: string | null, refreshMs?: number): Result<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const current = useRef(path);
  current.current = path;

  const load = useCallback(async () => {
    if (path === null) return;
    try {
      const result = await api.get<T>(path);
      // Si la ruta cambió mientras llegaba la respuesta, se descarta.
      if (current.current === path) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (current.current === path) setError((e as Error).message);
    } finally {
      if (current.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setData(null);
    setError(null);
    setLoading(path !== null);
    void load();
    if (!refreshMs || path === null) return;
    const timer = setInterval(() => void load(), refreshMs);
    return () => clearInterval(timer);
  }, [load, path, refreshMs]);

  return { data, error, loading, reload: load, setData };
}
