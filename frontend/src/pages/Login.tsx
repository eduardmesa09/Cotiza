import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/Layout";
import { Button, ErrorNotice, Field, Input } from "../components/ui";
import { homeFor } from "../lib/permissions";

export function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={homeFor(user.rol)} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const logged = await login(usuario, password);
      navigate(homeFor(logged.rol), { replace: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <aside className="relative hidden overflow-hidden bg-gradient-to-br from-navy via-brand-dark to-brand p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Logo light />
        <div>
          <p className="text-4xl font-semibold leading-tight tracking-tight">
            Cotizaciones a canales en minutos, no en horas.
          </p>
        </div>
        <p className="text-sm text-white/60">Prototipo académico · Universidad de La Sabana · Datos simulados</p>
      </aside>

      <main className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5">
          <div className="lg:hidden">
            <Logo />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Iniciar sesión</h1>
            <p className="mt-1 text-sm text-muted">Ingrese con su usuario de COTIZA+.</p>
          </div>
          <ErrorNotice message={error} />
          <Field label="Usuario">
            <Input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoFocus required />
          </Field>
          <Field label="Contraseña">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </Field>
          <Button type="submit" variant="primary" busy={busy} className="w-full">
            Ingresar
          </Button>
        </form>
      </main>
    </div>
  );
}
