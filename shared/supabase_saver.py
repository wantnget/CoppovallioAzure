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
    """Upsert de valida1 en Supabase. Idempotente por radicado (UNIQUE)."""
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


def save_motor_data_supabase(
    radicado_valida1: str | None, cedula: str, data: dict
) -> None:
    """Insert de motor_data en Supabase, vinculado al radicado de valida1."""
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
