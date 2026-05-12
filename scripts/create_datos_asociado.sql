-- Tabla: datos_asociado
-- Ejecutar en Supabase Dashboard → SQL Editor
-- Fuente: hoja "Base_Asociados" de Simulador_Analisis_Creditos_V3 2025.xlsx

CREATE TABLE IF NOT EXISTS datos_asociado (
    id                    BIGSERIAL    PRIMARY KEY,
    cedula                TEXT         NOT NULL UNIQUE,

    -- Datos personales
    primer_apellido       TEXT,
    nombre                TEXT,
    ciudad                TEXT,
    estado_civil          TEXT,           -- texto libre del Excel (ej. "Casado(a)")
    estado_civil_norm     TEXT,           -- versión normalizada (ej. "Casado(A)")
    edad                  INTEGER,
    personas_cargo        INTEGER,

    -- Datos laborales
    cliente_empresa       TEXT,
    fecha_ingreso         TEXT,           -- Fecha ingreso Cooperativa
    fecha_ingreso_empresa TEXT,           -- Fecha ingreso empresa/FVL
    antiguedad_coop       NUMERIC,        -- años, con decimales
    antiguedad_laboral    NUMERIC,

    -- Datos financieros
    salario               NUMERIC,
    aportes               NUMERIC,
    deuda_coopvalili      NUMERIC,
    usuario_credito       NUMERIC,        -- deuda activa en Coopvalili

    -- Vivienda y perfil
    tipo_vivienda         INTEGER,        -- código (1=propia, 2=arriendo, etc.)
    nivel                 NUMERIC,        -- ratio calculado en Excel (NULL si jubilado)

    -- Capacidad
    cuota_disponible      NUMERIC,        -- cuota disponible FVL (NULL si jubilado)

    -- Nombre completo (campo ASOCIADO del Excel)
    nombre_asociado       TEXT,

    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Índices útiles para búsquedas frecuentes
CREATE INDEX IF NOT EXISTS idx_datos_asociado_empresa
    ON datos_asociado (cliente_empresa);

CREATE INDEX IF NOT EXISTS idx_datos_asociado_ciudad
    ON datos_asociado (ciudad);

-- Comentario de tabla
COMMENT ON TABLE datos_asociado IS
    'Asociados cargados desde hoja Base_Asociados del Simulador Excel vía GitHub Actions';
