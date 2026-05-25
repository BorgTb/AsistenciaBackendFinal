CREATE SCHEMA IF NOT EXISTS "public";

CREATE TABLE "empresas" (
    "id" serial PRIMARY KEY,
    "nombre" varchar(100) NOT NULL,
    "rut_empresa" varchar(20),
    "email_contacto" varchar(100),
    "telefono" varchar(20),
    "direccion" varchar(200),
    "created_at" timestamp DEFAULT now()
);

CREATE TABLE "usuarios_web" (
    "id" serial PRIMARY KEY,
    "nombre" varchar(100) NOT NULL,
    "email" varchar(100) NOT NULL UNIQUE,
    "password_hash" varchar(200) NOT NULL,
    "activo" boolean DEFAULT true,
    "created_at" timestamp DEFAULT now()
);

CREATE TABLE "usuario_empresa" (
    "id" serial PRIMARY KEY,
    "usuario_id" integer NOT NULL REFERENCES "usuarios_web"("id") ON DELETE CASCADE,
    "empresa_id" integer NOT NULL REFERENCES "empresas"("id") ON DELETE CASCADE,
    "rol" varchar(20) NOT NULL DEFAULT 'trabajador',
    "activo" boolean DEFAULT true,
    "created_at" timestamp DEFAULT now(),
    UNIQUE("usuario_id", "empresa_id")
);

CREATE TABLE "dispositivos" (
    "id" serial PRIMARY KEY,
    "empresa_id" integer DEFAULT 1 REFERENCES "empresas"("id"),
    "nombre" varchar(100) DEFAULT 'Reloj Principal',
    "mac_address" varchar(20),
    "ip_local" varchar(20),
    "estado" varchar(20) DEFAULT 'activo',
    "ultimo_heartbeat" timestamp,
    "codigo_enrol" varchar(8),
    "enrolado" boolean DEFAULT true,
    "created_at" timestamp DEFAULT now()
);

CREATE TABLE "personas" (
    "id" serial PRIMARY KEY,
    "empresa_id" integer DEFAULT 1 REFERENCES "empresas"("id"),
    "nombre" varchar(100) NOT NULL,
    "rut" varchar(20) NOT NULL UNIQUE,
    "email" varchar(100),
    "huella_id" integer,
    "encoding_facial" text,
    "activo" boolean DEFAULT true,
    "created_at" timestamp DEFAULT now()
);

CREATE TABLE "turnos" (
    "id" serial PRIMARY KEY,
    "empresa_id" integer DEFAULT 1 REFERENCES "empresas"("id"),
    "nombre" varchar(100) NOT NULL,
    "hora_inicio" time NOT NULL,
    "hora_fin" time NOT NULL,
    "dias" varchar(50),
    "activo" boolean DEFAULT true,
    "created_at" timestamp DEFAULT now()
);

CREATE TABLE "asignaciones" (
    "id" serial PRIMARY KEY,
    "persona_id" integer REFERENCES "personas"("id"),
    "turno_id" integer REFERENCES "turnos"("id"),
    "fecha_asignacion" timestamp DEFAULT now(),
    "vigente" boolean DEFAULT true,
    UNIQUE("persona_id", "turno_id", "vigente")
);

CREATE TABLE "asistencias" (
    "id" serial PRIMARY KEY,
    "persona_id" integer REFERENCES "personas"("id"),
    "dispositivo_id" integer DEFAULT 1 REFERENCES "dispositivos"("id"),
    "nombre" varchar(100),
    "tipo" varchar(20),
    "metodo" varchar(50) DEFAULT 'huella',
    "fecha_hora" timestamp DEFAULT now(),
    "timestamp_local" varchar(50),
    "origen" varchar(20) DEFAULT 'dispositivo',
    "imagen_path" text,
    "sincronizado" boolean DEFAULT true,
    "sincronizado_at" timestamp
);

CREATE TABLE "sincronizacion_log" (
    "id" serial PRIMARY KEY,
    "dispositivo_id" integer DEFAULT 1 REFERENCES "dispositivos"("id"),
    "registros_enviados" integer DEFAULT 0,
    "registros_ok" integer DEFAULT 0,
    "estado" varchar(20) DEFAULT 'ok',
    "detalle" text,
    "fecha" timestamp DEFAULT now()
);

CREATE TABLE "integraciones_erp" (
    "id" serial PRIMARY KEY,
    "empresa_id" integer DEFAULT 1 REFERENCES "empresas"("id"),
    "nombre" varchar(120) NOT NULL,
    "tipo" varchar(40) NOT NULL,
    "webhook_url" text NOT NULL,
    "headers" text DEFAULT '{}',
    "field_map" text DEFAULT '{}',
    "envio_auto" boolean DEFAULT true,
    "activo" boolean DEFAULT true,
    "ultimo_envio" timestamp,
    "ultimo_estado" varchar(200),
    "created_at" timestamp DEFAULT now()
);

-- Índices
CREATE INDEX IF NOT EXISTS "idx_asistencias_persona" ON "asistencias" ("persona_id");
CREATE INDEX IF NOT EXISTS "idx_asistencias_dispositivo" ON "asistencias" ("dispositivo_id");
CREATE INDEX IF NOT EXISTS "idx_asistencias_fecha" ON "asistencias" ("fecha_hora");
CREATE INDEX IF NOT EXISTS "idx_personas_empresa" ON "personas" ("empresa_id");
CREATE INDEX IF NOT EXISTS "idx_erp_activo" ON "integraciones_erp" ("activo");
CREATE INDEX IF NOT EXISTS "idx_ue_usuario" ON "usuario_empresa" ("usuario_id");
CREATE INDEX IF NOT EXISTS "idx_ue_empresa" ON "usuario_empresa" ("empresa_id");
