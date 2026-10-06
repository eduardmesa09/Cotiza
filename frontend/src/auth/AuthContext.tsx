import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken, setUnauthorizedHandler } from "../lib/api";
import type { User } from "../lib/types";

interface AuthState {
  user: User | null;
  /** true mientras se comprueba si el token guardado sigue siendo válido. */
  loading: boolean;
  login: (usuario: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(() => getToken() !== null);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (getToken() === null) return;
    api
      .get<User>("/auth/me")
      .then(setUser)
      .catch(() => logout())
      .finally(() => setLoading(false));
  }, [logout]);

  const login = useCallback(async (usuario: string, password: string) => {
    const result = await api.post<{ access_token: string; usuario: User }>("/auth/login", { usuario, password });
    setToken(result.access_token);
    setUser(result.usuario);
    return result.usuario;
  }, []);

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth debe usarse dentro de AuthProvider");
  return context;
}

/** El usuario autenticado. Solo para pantallas que ya están detrás del inicio de sesión. */
export function useUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("No hay sesión iniciada");
  return user;
}
