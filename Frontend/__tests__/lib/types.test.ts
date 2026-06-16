import { describe, it, expect } from 'vitest';

describe('lib/types.ts', () => {
  it('AttendanceType is correct', () => {
    const entrada: import('@/lib/types').AttendanceType = 'entrada';
    const salida: import('@/lib/types').AttendanceType = 'salida';
    expect([entrada, salida]).toEqual(['entrada', 'salida']);
  });

  it('Persona type has correct fields', () => {
    const p: import('@/lib/types').Persona = {
      id: '1', nombre: 'Test', rut: '11.111.111-1', email: '',
      huella_id: 0, fecha_registro: '2026', sincronizado: true
    };
    expect(p.id).toBe('1');
    expect(p.sincronizado).toBe(true);
  });

  it('Asistencia type has correct fields', () => {
    const a: import('@/lib/types').Asistencia = {
      id: '1', persona_id: '1', nombre: 'Test', tipo: 'entrada',
      metodo: 'facial', fecha_hora: '2026', sincronizado: true
    };
    expect(a.tipo).toBe('entrada');
    expect(a.metodo).toBe('facial');
  });
});

describe('lib/auth-types.ts', () => {
  it('AuthUser type has correct fields', () => {
    const u: import('@/lib/auth-types').AuthUser = {
      id: 1, nombre: 'Admin', email: 'admin@test.cl', rol: 'admin',
      empresa_id: 1, empresa_nombre: 'Test Corp'
    };
    expect(u.rol).toBe('admin');
    expect(u.empresa_id).toBe(1);
  });

  it('EmpresaVinculada type', () => {
    const e: import('@/lib/auth-types').EmpresaVinculada = {
      empresa_id: 1, rol: 'admin', empresa_nombre: 'Empresa'
    };
    expect(e.empresa_id).toBe(1);
    expect(e.rol).toBe('admin');
  });
});
