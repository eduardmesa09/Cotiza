import { Pencil, UserPlus } from "lucide-react";
import { useState } from "react";
import { useUser } from "../auth/AuthContext";
import { Badge, Button, Card, ErrorNotice, Field, Input, Loading, Modal, PageHeader, Select, Table, TD, TH } from "../components/ui";
import { api } from "../lib/api";
import { ROLE_LABEL } from "../lib/permissions";
import type { AdminUser, Role } from "../lib/types";
import { useApi } from "../lib/useApi";

type Form = { id: number | null; usuario: string; nombre: string; email: string; rol: Role; activo: boolean; password: string };

const ROLES = Object.keys(ROLE_LABEL) as Role[];

export function Users() {
  const me = useUser();
  const { data, loading, error, reload } = useApi<AdminUser[]>("/usuarios");
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function edit(user?: AdminUser) {
    setFormError(null);
    setForm(user ? { ...user, password: "" } : { id: null, usuario: "", nombre: "", email: "", rol: "ejecutivo", activo: true, password: "" });
  }

  async function save() {
    if (!form) return;
    setBusy(true);
    setFormError(null);
    try {
      if (form.id === null) {
        await api.post("/usuarios", { usuario: form.usuario, nombre: form.nombre, email: form.email, rol: form.rol, password: form.password });
      } else {
        await api.put(`/usuarios/${form.id}`, {
          nombre: form.nombre,
          email: form.email,
          rol: form.rol,
          activo: form.activo,
          ...(form.password ? { password: form.password } : {}),
        });
      }
      setForm(null);
      await reload();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const set = (patch: Partial<Form>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const editingSelf = form?.id === me.id;

  return (
    <>
      <PageHeader
        title="Usuarios"
        subtitle="Cada usuario tiene un único rol; el rol define lo que puede hacer en el proceso."
        actions={
          <Button variant="primary" icon={<UserPlus className="size-4" />} onClick={() => edit()}>
            Nuevo usuario
          </Button>
        }
      />
      <Card className="p-0">
        <ErrorNotice message={error} />
        {loading && !data ? (
          <Loading />
        ) : (
          <Table
            head={
              <tr>
                <th className={`${TH} pl-5`}>Usuario</th>
                <th className={TH}>Nombre</th>
                <th className={TH}>Rol</th>
                <th className={TH}>Estado</th>
                <th className={`${TH} pr-5`} />
              </tr>
            }
          >
            {data?.map((user) => (
              <tr key={user.id}>
                <td className={`${TD} pl-5 font-semibold`}>{user.usuario}</td>
                <td className={TD}>
                  {user.nombre}
                  <span className="block text-xs text-muted">{user.email}</span>
                </td>
                <td className={TD}>{ROLE_LABEL[user.rol]}</td>
                <td className={TD}>{user.activo ? <Badge tone="ok">Activo</Badge> : <Badge>Inactivo</Badge>}</td>
                <td className={`${TD} pr-5 text-right`}>
                  <button type="button" onClick={() => edit(user)} aria-label={`Editar ${user.usuario}`} className="rounded-full p-1.5 text-muted hover:bg-canvas hover:text-ink">
                    <Pencil className="size-4" />
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {form && (
        <Modal
          title={form.id === null ? "Nuevo usuario" : `Editar ${form.usuario}`}
          onClose={() => setForm(null)}
          footer={
            <>
              <Button onClick={() => setForm(null)}>Cancelar</Button>
              <Button variant="primary" busy={busy} onClick={save}>
                Guardar
              </Button>
            </>
          }
        >
          <ErrorNotice message={formError} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Usuario" hint={form.id === null ? "Minúsculas, números, punto o guion." : undefined}>
              <Input value={form.usuario} disabled={form.id !== null} onChange={(e) => set({ usuario: e.target.value.toLowerCase() })} />
            </Field>
            <Field label="Rol">
              <Select value={form.rol} disabled={editingSelf} onChange={(e) => set({ rol: e.target.value as Role })}>
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {ROLE_LABEL[role]}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Nombre">
            <Input value={form.nombre} onChange={(e) => set({ nombre: e.target.value })} />
          </Field>
          <Field label="Correo">
            <Input type="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
          </Field>
          <Field label={form.id === null ? "Contraseña" : "Nueva contraseña"} hint={form.id === null ? "Mínimo 8 caracteres." : "Déjela vacía para no cambiarla."}>
            <Input type="password" value={form.password} autoComplete="new-password" onChange={(e) => set({ password: e.target.value })} />
          </Field>
          {form.id !== null && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.activo} disabled={editingSelf} onChange={(e) => set({ activo: e.target.checked })} className="size-4 accent-brand" />
              Usuario activo
              {editingSelf && <span className="text-xs text-muted">(no puede desactivarse a sí mismo)</span>}
            </label>
          )}
        </Modal>
      )}
    </>
  );
}
