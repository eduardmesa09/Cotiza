import { Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { formatMoney } from "../lib/format";
import type { Product } from "../lib/types";
import { useApi } from "../lib/useApi";
import { Badge, Button, ErrorNotice, Loading } from "./ui";

interface Props {
  onSelect: (product: Product) => void;
  /** Referencias ya agregadas: se muestran, pero no se pueden repetir. */
  exclude: string[];
}

/** Catálogo completo, una pestaña por categoría, para agregar referencias sin buscarlas. */
export function CatalogBrowser({ onSelect, exclude }: Props) {
  const catalog = useApi<Product[]>("/catalogo?limite=1000");
  const [selected, setSelected] = useState<string | null>(null);

  const groups = useMemo(() => {
    const byCategory = new Map<string, Product[]>();
    for (const product of catalog.data ?? []) {
      const list = byCategory.get(product.categoria) ?? [];
      list.push(product);
      byCategory.set(product.categoria, list);
    }
    return [...byCategory.entries()].sort(([a], [b]) => a.localeCompare(b, "es"));
  }, [catalog.data]);

  if (catalog.loading) return <Loading label="Cargando catálogo…" />;
  if (catalog.error) return <ErrorNotice message={`No se pudo cargar el catálogo: ${catalog.error}`} />;
  if (groups.length === 0) return <p className="py-6 text-center text-sm text-muted">El catálogo no tiene referencias.</p>;

  const active = groups.find(([name]) => name === selected) ?? groups[0];
  const [category, products] = active;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Categorías del catálogo">
        {groups.map(([name, items]) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={name === category}
            onClick={() => setSelected(name)}
            className={`rounded-full px-3 py-1.5 text-sm font-medium ${name === category ? "bg-brand-dark text-white" : "bg-canvas text-muted hover:text-ink"}`}
          >
            {name} <span className="nums opacity-70">{items.length}</span>
          </button>
        ))}
      </div>
      <ul role="tabpanel" aria-label={category} className="max-h-96 divide-y divide-line overflow-y-auto rounded-xl border border-line">
        {products.map((product) => {
          const added = exclude.includes(product.referencia);
          return (
            <li key={product.referencia} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
              <span className="min-w-0">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-ink">{product.referencia}</span>
                  {product.precio_lista != null && <span className="nums font-medium text-ink">{formatMoney(product.precio_lista)}</span>}
                </span>
                <span className="block truncate text-xs text-muted" title={product.descripcion}>
                  {product.descripcion}
                </span>
              </span>
              <span className="shrink-0">
                {!product.cotizable ? (
                  <Badge tone="bad">No cotizable</Badge>
                ) : added ? (
                  <Badge>Ya agregada</Badge>
                ) : (
                  <Button size="sm" className="!px-2" icon={<Plus className="size-4" />} aria-label={`Agregar ${product.referencia}`} title="Agregar a la cotización" onClick={() => onSelect(product)} />
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
