import os

import requests

from .logger import get_logger

log = get_logger(__name__)


def _headers(upsert: bool = False) -> dict:
    key = os.environ.get("SUPABASE_KEY", "")
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    if upsert:
        h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    return h


def _base_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL no configurado")
    if not os.environ.get("SUPABASE_KEY", ""):
        raise RuntimeError("SUPABASE_KEY no configurado")
    return f"{url}/rest/v1"


def save_valida1_supabase(radicado: str, cedula: str, data: dict) -> None:
    result = data.get("result") or {}
    datos = data.get("datos_asociado") or {}

    row = {
        "radicado": radicado,
        "cedula": cedula,
        # result
        "valida_id": result.get("valida_id"),
        "valida_edad": result.get("valida_edad"),
        "valida_antiguedad": result.get("valida_antiguedad"),
        "valida_no_retirado": result.get("valida_no_retirado"),
        "valida1": result.get("valida1"),
        "mensaje": result.get("mensaje"),
        # datos_asociado
        "fecha_generacion": datos.get("fecha_generacion"),
        "tipo_identificacion": datos.get("tipo_identificacion"),
        "numero_identificacion": datos.get("numero_identificacion"),
        "cliente_empresa": datos.get("cliente_empresa"),
        "primer_apellido": datos.get("primer_apellido"),
        "segundo_apellido": datos.get("segundo_apellido"),
        "nombre": datos.get("nombre"),
        "fecha_ingreso": datos.get("fecha_ingreso"),
        "fecha_ingreso_empresa": datos.get("fecha_ingreso_empresa"),
        "telefono": datos.get("telefono"),
        "direccion": datos.get("direccion"),
        "asociado": datos.get("asociado"),
        "activo": datos.get("activo"),
        "actividad_economica": str(datos.get("actividadEconomica", "") or ""),
        "codigo_municipal": datos.get("codigoMunicipal"),
        "email": datos.get("email"),
        "genero": datos.get("genero"),
        "empleado": datos.get("empleado"),
        "tipo_contrato": datos.get("tipoContrato"),
        "nivel_escolar": datos.get("nivelEscolar"),
        "estrato": datos.get("estrato"),
        "fecha_nacimiento": datos.get("fechaNacimiento"),
        "estado_civil": datos.get("estadoCivil"),
        "mujer_cabeza_familia": datos.get("mujerCabezaFamilia"),
        "sector_economico": datos.get("sectorEconomico"),
        "jornada_laboral": datos.get("jornadaLaboral"),
        "fecha_retiro": datos.get("fechaRetiro"),
        "celular": datos.get("celular"),
        "raw_json": data,
    }

    resp = requests.post(
        f"{_base_url()}/valida1_results",
        headers=_headers(upsert=True),
        json=row,
        timeout=10,
    )
    resp.raise_for_status()
    log.info("supabase valida1 guardado", extra={"radicado": radicado})


def save_identity_supabase(radicado: str, cedula: str, data: dict) -> None:
    row = {
        "radicado_valida1": radicado,
        "cedula": cedula,
        "tipo_validacion": data.get("tipo_validacion"),
        "status_document": data.get("status_document"),
        "status_face": data.get("status_face"),
        "estado_validacion": data.get("estado_validacion"),
        "request_json": data.get("request_json"),
    }

    resp = requests.post(
        f"{_base_url()}/identity_validations?on_conflict=radicado_valida1",
        headers=_headers(upsert=True),
        json=row,
        timeout=10,
    )
    resp.raise_for_status()
    log.info("supabase identity guardado", extra={"radicado": radicado})


def save_motor_data_supabase(
    radicado_valida1: str | None, cedula: str, data: dict
) -> None:
    detallado = data.get("detallado_want") or {}
    meta = data.get("meta") or {}

    row = {
        "radicado_valida1": radicado_valida1,
        "cedula": cedula,
        "status": data.get("status"),
        # detallado_want
        "garantia": detallado.get("garantia"),
        "aportes": detallado.get("aportes"),
        "aporte_mensual": detallado.get("aporteMensual"),
        "deuda_coopvalili": detallado.get("deudaCoopvalili"),
        "deuda_sector": detallado.get("deudaSector"),
        "deuda_tc_sector": detallado.get("deudaTcsector"),
        "cupos_tdc": detallado.get("cuposTdc"),
        "cuota_recoge_coopvalili": detallado.get("cuotarecogeCoopvalili"),
        "cuota_recoge_sector": detallado.get("cuotarecogeSector"),
        "salario": detallado.get("salario"),
        "tipo_salario": detallado.get("tipoSalario"),
        "egresos_volante": detallado.get("egresosVolante"),
        "egresos_sector": detallado.get("egresosSector"),
        "score_cifin": detallado.get("scoreCifin"),
        "frecuencia_pagos": detallado.get("frecuenciaPagos"),
        "aportes_ahorros": detallado.get("aportesAhorros"),
        "linea_credito": detallado.get("lineaCredito"),
        "monto_solicitado": detallado.get("montoSolicitado"),
        "parametro_credito": detallado.get("parametroCredito"),
        "instancia_aprobacion": detallado.get("instanciaAprobacion"),
        "ahorros_fondo": detallado.get("ahorrosFondo"),
        "fecha_ingreso": detallado.get("fechaIngreso"),
        "fecha_nacimiento": detallado.get("fechaNacimiento"),
        "edad": detallado.get("edad"),
        "personas_cargo": detallado.get("personasCargo"),
        "tipo_vivienda": detallado.get("tipoVivienda"),
        "antiguedad_fondo": detallado.get("antiguedadFondo"),
        "antiguedad_laboral": detallado.get("antiguedadLaboral"),
        "tasa_usura": detallado.get("tasaUsura"),
        "tasa_usura_per": detallado.get("tasausuraper"),
        "plazo_tarjetas": detallado.get("plazoTarjetas"),
        # meta
        "meta_coopvalili": meta.get("coopvalili"),
        "meta_transunion": meta.get("transunion"),
        "meta_mensaje": meta.get("mensaje"),
        "raw_json": data,
    }

    resp = requests.post(
        f"{_base_url()}/motor_data_results",
        headers=_headers(),
        json=row,
        timeout=10,
    )
    resp.raise_for_status()
    log.info("supabase motor_data guardado", extra={"cedula": cedula})


def save_motor_process_supabase(radicado: str, cedula: str, data: dict) -> None:
    processing = data.get("processing") or {}
    meta = data.get("meta") or {}

    row = {
        "radicado": radicado,
        "cedula": cedula,
        "status": data.get("status"),
        # Scores y Perfil
        "perfil": processing.get("PERFIL"),
        "totales_scor": processing.get("TOTALES_SCOR"),
        "usario_credito": processing.get("USARIO_CREDITO"),
        "scor_nivel_riesgo": processing.get("SCOR_NIVEL_RIESGO"),
        "scor_edad": processing.get("SCOR_EDAD"),
        "scor_pcargo": processing.get("SCOR_PCARGO"),
        "scor_vivienda": processing.get("SCOR_VIVIENDA"),
        "scor_ant_coop": processing.get("SCOR_ANT_COOP"),
        "scor_ant_laboral": processing.get("SCOR_ANT_LABORAL"),
        "scor_ingresos": processing.get("SCOR_INGRESOS"),
        # Ingresos y Egresos
        "ingresos": processing.get("Ingresos"),
        "egresos": processing.get("Egresos"),
        "minimo_vital": processing.get("Mínimo Vital"),
        "resumen_salarial": processing.get("Resumen Salarial del Asociado"),
        "cuota_tdc": processing.get("Cuota TDC"),
        "descuentos_ley": processing.get("Descuentos de Ley"),
        # Cuotas y Montos
        "cuota_max_endeudamiento_mensual": processing.get("Cuota Máximo por Endeudamiento Mensual"),
        "cuota_max_endeudamiento_periodica": processing.get("Cuota Máximo por Endeudamiento Periódica"),
        "cuota_max_capacidad_mensual": processing.get("Cuota Máxima por Capacidad Mensual"),
        "cuota_max_capacidad_periodica": processing.get("Cuota Máxima por Capacidad Periódica"),
        "cuota_max_capacidad": processing.get("Cuota Máxima por Capacidad"),
        "cuota_periodica_solicitada": processing.get("Cuota Periodica Solicitada"),
        "cuota_definitiva": processing.get("Cuota definitiva"),
        # Límites de Deuda
        "maximo_deuda_endeudamiento": processing.get("Maximo Deuda por Endeudamiento"),
        "maximo_deuda_desprotegido": processing.get("Maximo Deuda por Desprotegido"),
        "valor_final_credito_motor": processing.get("Valor Final del Crédito por Motor"),
        "valor_desprotegido_max_linea": processing.get("VALOR DESPROTEGIDO MAX DE LA LINEA"),
        "total_ahorros_prestaciones": processing.get("Total Ahorros+Prestaciones"),
        # Monto Definitivo y Reglas
        "regla1_monto_motor_ge_solicitud": processing.get("Regla 1 monto_motor > = monto_solicitud"),
        "regla2_monto_motor_ge_param": processing.get("Regla 2 monto_motor > = param"),
        "regla3_param_ge_monto_motor": processing.get("Regla 3 param > = monto_motor"),
        "monto_definitivo": processing.get("Monto definitivo"),
        # Endeudamiento
        "endeudamiento_actual": processing.get("Endeudamiento Actual"),
        "endeudamiento_actual_cupo": processing.get("Endeudamiento Actual con Cupo Coopvalili"),
        "endeudamiento_proyectado": processing.get("Endeudamiento Proyectado"),
        "endeudamiento_proyectado_cupo": processing.get("Endeudamiento Proyectado Con Cupo Coopvalili"),
        "maximo_endeudamiento": processing.get("Máximo Endeudamiento"),
        # Cumplimiento de Criterios
        "cumple_end": processing.get("cumple_end"),
        "cumple_sol": processing.get("cumple_sol"),
        "cumple_disp": processing.get("cumple_disp"),
        "cumple_des": processing.get("cumple_des"),
        "cumplimiento_4_criterios": processing.get("Cumplimiento 4 criterios"),
        # Solvencia y Disponible
        "solvencia": processing.get("Solvencia"),
        "disponible": processing.get("Disponible"),
        # Desprotegido
        "desprotegido": processing.get("Desprotegido"),
        "desprotegido_maximo": processing.get("Desprotegido Máximo"),
        # Concepto Final
        "concepto_definitivo": processing.get("Concepto definitivo"),
        "viable_cmd": processing.get("VIABLE  CMD"),
        # Bloque 1
        "egresos_volante_ajustado_b1": processing.get("Egresos volante ajustado_1"),
        "total_egresos_b1": processing.get("Total egresos_1"),
        "capacidad_pago_b1": processing.get("Capacidad de pago_1"),
        "monto_credito_b1_pre": processing.get("Monto credito_1_pre"),
        "monto_credito_b1": processing.get("Monto credito_1"),
        "endeudamiento_proyectado_b1": processing.get("Endeudamiento Proyectado_b1"),
        "cumple_end_b1": processing.get("cumple_end_b1"),
        "cumple_sol_b1": processing.get("cumple_sol_b1"),
        "cumple_disp_b1": processing.get("cumple_disp_b1"),
        "cumple_des_b1": processing.get("cumple_des_b1"),
        "cumple_4_criterios_b1": processing.get("Cumple 4 criterios_b1"),
        "solvencia_b1": processing.get("Solvencia_b1"),
        "desprotegido_b1": processing.get("desprotegido_b1"),
        # Bloque 2
        "total_egresos_b2": processing.get("Total egresos_2"),
        "capacidad_pago_b2": processing.get("Capacidad de pago_2"),
        "monto_credito_b2_pre": processing.get("Monto credito_2_pre"),
        "monto_credito_b2": processing.get("Monto credito_2"),
        "endeudamiento_proyectado_b2": processing.get("Endeudamiento Proyectado_b2"),
        "cumple_end_b2": processing.get("cumple_end_b2"),
        "cumple_sol_b2": processing.get("cumple_sol_b2"),
        "cumple_disp_b2": processing.get("cumple_disp_b2"),
        "cumple_des_b2": processing.get("cumple_des_b2"),
        "cumple_4_criterios_b2": processing.get("Cumple 4 criterios_b2"),
        "solvencia_b2": processing.get("Solvencia_b2"),
        "desprotegido_b2": processing.get("desprotegido_b2"),
        # Bloque 3
        "total_egresos_b3": processing.get("Total egresos_3"),
        "capacidad_pago_b3": processing.get("Capacidad de pago_3"),
        "monto_credito_b3_pre": processing.get("Monto credito_3_pre"),
        "monto_credito_b3": processing.get("Monto credito_3"),
        "endeudamiento_proyectado_b3": processing.get("Endeudamiento Proyectado_b3"),
        "cumple_end_b3": processing.get("cumple_end_b3"),
        "cumple_sol_b3": processing.get("cumple_sol_b3"),
        "cumple_disp_b3": processing.get("cumple_disp_b3"),
        "cumple_des_b3": processing.get("cumple_des_b3"),
        "cumple_4_criterios_b3": processing.get("Cumple 4 criterios_b3"),
        "solvencia_b3": processing.get("Solvencia_b3"),
        "desprotegido_b3": processing.get("desprotegido_b3"),
        "raw_json": data,
    }

    resp = requests.post(
        f"{_base_url()}/motor_process_results",
        headers=_headers(upsert=True),
        json=row,
        timeout=10,
    )
    resp.raise_for_status()
    log.info("supabase motor_process guardado", extra={"radicado": radicado})
