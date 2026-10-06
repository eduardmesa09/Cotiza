import { Search } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { api } from "../lib/api";
import { formatMoney } from "../lib/format";
import type { Product } from "../lib/types";
import { Badge } from "./ui";

interface Props {
  onSelect: (product: Product) => void;
  /** Referencias ya agregadas: se muestran, pero no se pueden repetir. */
  exclude: string[];
  autoFocus?: boolean;
}

/** Buscador de referencias con autocompletado por código o descripción (M1). */
export function ProductSearch({ onSelect, exclude, autoFocus }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [searching, setSearching] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const listId = useId();

  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    let cancelled = false;
    // Espera breve: no se consulta en cada tecla.
    const timer = setTimeout(async () => {
      try {
        const found = await api.get<Product[]>(`/catalogo?q=${encodeURIComponent(text)}&limite=12`);
        if (!cancelled) {
          setResults(found);
          setActive(0);
        }
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 200);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  const selectable = (p: Product) => p.cotizable && !exclude.includes(p.referencia);

  function choose(product: Product) {
    if (!selectable(product)) return;
    onSelect(product);
    setQuery("");
    setResults([]);
    setOpen(false);
    inputRef.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && results[active]) {
      event.preventDefault();
      choose(results[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const showList = open && query.trim().length >= 2;

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
      <input
        ref={inputRef}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-label="Buscar referencia por código o descripción"
        placeholder="Buscar referencia por código o descripción…"
        value={query}
        autoFocus={autoFocus}
        onChange={(e) => {
          clearTimeout(closeTimer.current);
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          // Si se vuelve al campo antes de que venza el cierre diferido, se cancela.
          clearTimeout(closeTimer.current);
          setOpen(true);
        }}
        // Cierre diferido: deja tiempo a que el clic sobre una opción se registre.
        onBlur={() => {
          closeTimer.current = setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={onKeyDown}
        className="w-full rounded-full border border-line bg-surface py-2.5 pl-10 pr-4 text-sm placeholder:text-slate-400 focus:border-brand focus:outline-2 focus:outline-brand/25"
      />
      {showList && (
        <ul id={listId} role="listbox" className="absolute z-20 mt-2 max-h-80 w-full overflow-y-auto rounded-2xl bg-surface py-1 shadow-2xl ring-1 ring-line">
          {results.length === 0 && (
            <li className="px-4 py-3 text-sm text-muted">{searching ? "Buscando…" : "Sin coincidencias en el catálogo."}</li>
          )}
          {results.map((product, index) => {
            const added = exclude.includes(product.referencia);
            return (
              <li
                key={product.referencia}
                role="option"
                aria-selected={index === active}
                aria-disabled={!selectable(product)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(product)}
                onMouseEnter={() => setActive(index)}
                className={`flex items-center justify-between gap-3 px-4 py-2.5 text-sm ${
                  selectable(product) ? "cursor-pointer" : "cursor-not-allowed opacity-60"
                } ${index === active ? "bg-canvas" : ""}`}
              >
                <span className="min-w-0">
                  <span className="font-semibold text-ink">{product.referencia}</span>
                  <span className="ml-2 text-muted">{product.categoria}</span>
                  <span className="block truncate text-ink">{product.descripcion}</span>
                </span>
                <span className="shrink-0 text-right">
                  {!product.cotizable ? (
                    <Badge tone="bad">No cotizable</Badge>
                  ) : added ? (
                    <Badge>Ya agregada</Badge>
                  ) : (
                    <span className="nums font-medium text-ink">{formatMoney(product.precio_lista)}</span>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
