CREATE TABLE IF NOT EXISTS valida1_results (
    id                    BIGSERIAL    PRIMARY KEY,
    radicado              TEXT         NOT NULL UNIQUE,
    cedula                TEXT         NOT NULL,

    -- bloque result
    valida_id             SMALLINT,
    valida_edad           SMALLINT,
    valida_antiguedad     SMALLINT,
    valida_no_retirado    SMALLINT,
    valida1               SMALLINT,
    mensaje               TEXT,

    -- bloque datos_asociado
    fecha_generacion      TEXT,
    tipo_identificacion   TEXT,
    numero_identificacion TEXT,
    cliente_empresa       TEXT,
    primer_apellido       TEXT,
    segundo_apellido      TEXT,
    nombre                TEXT,
    fecha_ingreso         TEXT,
    fecha_ingreso_empresa TEXT,
    telefono              TEXT,
    direccion             TEXT,
    asociado              SMALLINT,
    activo                SMALLINT,
    actividad_economica   TEXT,
    codigo_municipal      INTEGER,
    email                 TEXT,
    genero                SMALLINT,
    empleado              SMALLINT,
    tipo_contrato         SMALLINT,
    nivel_escolar         SMALLINT,
    estrato               SMALLINT,
    fecha_nacimiento      TEXT,
    estado_civil          SMALLINT,
    mujer_cabeza_familia  SMALLINT,
    sector_economico      INTEGER,
    jornada_laboral       SMALLINT,
    fecha_retiro          TEXT,
    celular               TEXT,

    raw_json              JSONB,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_valida1_cedula ON valida1_results (cedula);

CREATE TABLE IF NOT EXISTS motor_data_results (
    id                      BIGSERIAL   PRIMARY KEY,
    radicado_valida1        TEXT        REFERENCES valida1_results (radicado) ON DELETE SET NULL,
    cedula                  TEXT        NOT NULL,
    status                  TEXT,

    -- bloque detallado_want
    garantia                TEXT,
    aportes                 NUMERIC,
    aporte_mensual          NUMERIC,
    deuda_coopvalili        NUMERIC,
    deuda_sector            NUMERIC,
    deuda_tc_sector         NUMERIC,
    cupos_tdc               NUMERIC,
    cuota_recoge_coopvalili NUMERIC,
    cuota_recoge_sector     NUMERIC,
    salario                 NUMERIC,
    tipo_salario            TEXT,
    egresos_volante         NUMERIC,
    egresos_sector          NUMERIC,
    score_cifin             INTEGER,
    frecuencia_pagos        TEXT,
    aportes_ahorros         NUMERIC,
    linea_credito           TEXT,
    monto_solicitado        NUMERIC,
    parametro_credito       NUMERIC,
    instancia_aprobacion    TEXT,
    ahorros_fondo           NUMERIC,
    fecha_ingreso           TEXT,
    fecha_nacimiento        TEXT,
    edad                    INTEGER,
    personas_cargo          INTEGER,
    tipo_vivienda           INTEGER,
    antiguedad_fondo        NUMERIC,
    antiguedad_laboral      NUMERIC,
    tasa_usura              NUMERIC,
    tasa_usura_per          NUMERIC,
    plazo_tarjetas          INTEGER,

    -- bloque meta
    meta_coopvalili         TEXT,
    meta_transunion         TEXT,
    meta_mensaje            TEXT,

    raw_json                JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_motor_data_cedula   ON motor_data_results (cedula);
CREATE INDEX IF NOT EXISTS idx_motor_data_radicado ON motor_data_results (radicado_valida1);