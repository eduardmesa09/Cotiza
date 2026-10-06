import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { canAccess, homeFor } from "./lib/permissions";
import { Approvals } from "./pages/Approvals";
import { Dashboard } from "./pages/Dashboard";
import { FollowUp } from "./pages/FollowUp";
import { Login } from "./pages/Login";
import { ParametersPage, Pricing } from "./pages/Pricing";
import { QuotePage } from "./pages/QuotePage";
import { QuotesList } from "./pages/QuotesList";
import { Users } from "./pages/Users";

/** Exige sesión y que el rol tenga acceso a la ruta; si no, lleva a la pantalla de inicio del rol. */
function Guard() {
  const { user, loading } = useAuth();
  const { pathname } = useLocation();
  if (loading) return <Loading label="Verificando sesión…" />;
  if (!user) return <Navigate to="/login" replace />;
  if (pathname === "/" || !canAccess(user.rol, pathname)) return <Navigate to={homeFor(user.rol)} replace />;
  return <Outlet />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Guard />}>
        <Route element={<Layout />}>
          <Route path="/cotizaciones" element={<QuotesList />} />
          {/* Una sola ruta para "nueva" y para una existente: al calcular por primera vez la
              pantalla no se vuelve a montar ni parpadea. */}
          <Route path="/cotizaciones/:id" element={<QuotePage />} />
          <Route path="/aprobaciones" element={<Approvals />} />
          <Route path="/seguimiento" element={<FollowUp />} />
          <Route path="/pricing" element={<Pricing />} />
          <Route path="/usuarios" element={<Users />} />
          <Route path="/parametros" element={<ParametersPage />} />
          <Route path="/tablero" element={<Dashboard />} />
        </Route>
        <Route path="*" element={null} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
