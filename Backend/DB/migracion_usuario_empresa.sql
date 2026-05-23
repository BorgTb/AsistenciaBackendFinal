-- ============================================================
-- MIGRACIÓN: Relación N:N usuarios_web <-> empresas
-- Ejecutar este script en la base de datos PostgreSQL (Neon)
-- ============================================================

-- 1. Crear tabla de relación usuario-empresa (muchos a muchos)
CREATE TABLE IF NOT EXISTS usuario_empresa (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios_web(id) ON DELETE CASCADE,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    rol VARCHAR(20) NOT NULL DEFAULT 'trabajador',
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(usuario_id, empresa_id)
);

-- 2. Migrar datos existentes: por cada usuario con empresa_id no nulo,
--    insertar en usuario_empresa si no existe ya
INSERT INTO usuario_empresa (usuario_id, empresa_id, rol, activo)
SELECT u.id, u.empresa_id, u.rol, u.activo
FROM usuarios_web u
WHERE u.empresa_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM usuario_empresa ue
    WHERE ue.usuario_id = u.id AND ue.empresa_id = u.empresa_id
  );

-- 3. Hacer nullable empresa_id en usuarios_web (ahora el rol y empresa viven en la tabla pivote)
ALTER TABLE usuarios_web ALTER COLUMN empresa_id DROP NOT NULL;
ALTER TABLE usuarios_web DROP COLUMN IF EXISTS rol;

-- 4. Agregar índice para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_usuario_empresa_usuario ON usuario_empresa(usuario_id);
CREATE INDEX IF NOT EXISTS idx_usuario_empresa_empresa ON usuario_empresa(empresa_id);

-- 5. Verificar migración
SELECT 'Migración completada. Usuarios migrados:' AS mensaje, COUNT(*) AS total FROM usuario_empresa;
