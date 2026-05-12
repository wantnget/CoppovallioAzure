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

CREATE TABLE IF NOT EXISTS identity_validations (
    id                BIGSERIAL   PRIMARY KEY,
    radicado_valida1  TEXT        UNIQUE REFERENCES valida1_results (radicado) ON DELETE SET NULL,
    cedula            TEXT        NOT NULL,
    tipo_validacion   TEXT,
    status_document   SMALLINT,
    status_face       SMALLINT,
    estado_validacion SMALLINT,
    request_json      JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_identity_cedula    ON identity_validations (cedula);
CREATE INDEX IF NOT EXISTS idx_identity_radicado  ON identity_validations (radicado_valida1);

CREATE TABLE IF NOT EXISTS motor_process_results (
    id                          BIGSERIAL   PRIMARY KEY,
    radicado                    TEXT        NOT NULL UNIQUE,
    cedula                      TEXT        NOT NULL,
    status                      TEXT,

    -- Scores y Perfil
    perfil                      TEXT,
    totales_scor                NUMERIC,
    usario_credito              NUMERIC,
    scor_nivel_riesgo           NUMERIC,
    scor_edad                   NUMERIC,
    scor_pcargo                 NUMERIC,
    scor_vivienda               NUMERIC,
    scor_ant_coop               NUMERIC,
    scor_ant_laboral            NUMERIC,
    scor_ingresos               NUMERIC,

    -- Ingresos y Egresos
    ingresos                    NUMERIC,
    egresos                     NUMERIC,
    minimo_vital                NUMERIC,
    resumen_salarial            NUMERIC,
    cuota_tdc                   NUMERIC,
    descuentos_ley              NUMERIC,

    -- Cuotas y Montos
    cuota_max_endeudamiento_mensual     NUMERIC,
    cuota_max_endeudamiento_periodica   NUMERIC,
    cuota_max_capacidad_mensual         NUMERIC,
    cuota_max_capacidad_periodica       NUMERIC,
    cuota_max_capacidad                 NUMERIC,
    cuota_periodica_solicitada          NUMERIC,
    cuota_definitiva                    NUMERIC,

    -- Límites de Deuda
    maximo_deuda_endeudamiento          NUMERIC,
    maximo_deuda_desprotegido           NUMERIC,
    valor_final_credito_motor           NUMERIC,
    valor_desprotegido_max_linea        NUMERIC,
    total_ahorros_prestaciones          NUMERIC,

    -- Monto Definitivo y Reglas
    regla1_monto_motor_ge_solicitud     SMALLINT,
    regla2_monto_motor_ge_param         SMALLINT,
    regla3_param_ge_monto_motor         SMALLINT,
    monto_definitivo                    NUMERIC,

    -- Endeudamiento
    endeudamiento_actual                NUMERIC,
    endeudamiento_actual_cupo           NUMERIC,
    endeudamiento_proyectado            NUMERIC,
    endeudamiento_proyectado_cupo       NUMERIC,
    maximo_endeudamiento                NUMERIC,

    -- Cumplimiento de Criterios
    cumple_end                          SMALLINT,
    cumple_sol                          SMALLINT,
    cumple_disp                         SMALLINT,
    cumple_des                          SMALLINT,
    cumplimiento_4_criterios            SMALLINT,

    -- Solvencia y Disponible
    solvencia                           NUMERIC,
    disponible                          NUMERIC,

    -- Desprotegido
    desprotegido                        NUMERIC,
    desprotegido_maximo                 NUMERIC,

    -- Concepto Final
    concepto_definitivo                 TEXT,
    viable_cmd                          NUMERIC,

    -- Bloque 1
    egresos_volante_ajustado_b1         NUMERIC,
    total_egresos_b1                    NUMERIC,
    capacidad_pago_b1                   NUMERIC,
    monto_credito_b1_pre                NUMERIC,
    monto_credito_b1                    NUMERIC,
    endeudamiento_proyectado_b1         NUMERIC,
    cumple_end_b1                       SMALLINT,
    cumple_sol_b1                       SMALLINT,
    cumple_disp_b1                      SMALLINT,
    cumple_des_b1                       SMALLINT,
    cumple_4_criterios_b1               SMALLINT,
    solvencia_b1                        NUMERIC,
    desprotegido_b1                     NUMERIC,

    -- Bloque 2
    total_egresos_b2                    NUMERIC,
    capacidad_pago_b2                   NUMERIC,
    monto_credito_b2_pre                NUMERIC,
    monto_credito_b2                    NUMERIC,
    endeudamiento_proyectado_b2         NUMERIC,
    cumple_end_b2                       SMALLINT,
    cumple_sol_b2                       SMALLINT,
    cumple_disp_b2                      SMALLINT,
    cumple_des_b2                       SMALLINT,
    cumple_4_criterios_b2               SMALLINT,
    solvencia_b2                        NUMERIC,
    desprotegido_b2                     NUMERIC,

    -- Bloque 3
    total_egresos_b3                    NUMERIC,
    capacidad_pago_b3                   NUMERIC,
    monto_credito_b3_pre                NUMERIC,
    monto_credito_b3                    NUMERIC,
    endeudamiento_proyectado_b3         NUMERIC,
    cumple_end_b3                       SMALLINT,
    cumple_sol_b3                       SMALLINT,
    cumple_disp_b3                      SMALLINT,
    cumple_des_b3                       SMALLINT,
    cumple_4_criterios_b3               SMALLINT,
    solvencia_b3                        NUMERIC,
    desprotegido_b3                     NUMERIC,

    raw_json                            JSONB,
    created_at                          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_motor_process_cedula    ON motor_process_results (cedula);
CREATE INDEX IF NOT EXISTS idx_motor_process_status    ON motor_process_results (status);
