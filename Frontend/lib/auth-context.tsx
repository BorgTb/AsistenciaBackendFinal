'use client';

import type { ReactNode } from 'react';
import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { AuthUser, EmpresaVinculada } from '@/lib/auth-types';
import { clearToken, fetchMe, hasToken, loginRequest, saveToken, type LoginNeedEmpresa, type LoginSuccess } from '@/lib/auth-api';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string, empresaId?: number) => Promise<LoginSuccess | LoginNeedEmpresa>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: async () => ({ ok: false, need_empresa: true, empresas: [], user_name: '', user_email: '' }),
  logout: () => {}
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!hasToken()) {
      setLoading(false);
      return;
    }

    fetchMe()
      .then((data) => setUser(data.user))
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string, empresaId?: number): Promise<LoginSuccess | LoginNeedEmpresa> => {
    const result = await loginRequest(email, password, empresaId);

    if (result.ok) {
      saveToken(result.token);
      setUser(result.user);
    }

    return result;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
