export interface EmpresaVinculada {
  empresa_id: number;
  rol: 'admin' | 'empleador' | 'trabajador';
  empresa_nombre: string;
}

export interface AuthUser {
  id: number;
  nombre: string;
  email: string;
  rol: 'admin' | 'empleador' | 'trabajador';
  empresa_id: number;
  empresa_nombre: string;
  persona_id?: number | null;
  empresas?: EmpresaVinculada[];
}

export interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
}
