import json
import os
import math
import datetime
from typing import Any

import numpy_financial as npf
from dateutil.relativedelta import relativedelta
import azure.functions as func

from shared.auth import validar_api_key
from shared.exceptions import AuthError
from shared.logger import get_logger
from shared.blob_loader import save_json_blob_by_id
from shared.supabase_saver import save_motor_process_supabase

log = get_logger("motor_process")


def _to_date(v):
    """Acepta date, datetime o string en varios formatos comunes."""
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(v, fmt).date()
            except ValueError:
                continue
    return v


def _floor_to(x, multiple):
    if multiple == 0:
        return 0
    return math.floor(x / multiple) * multiple


def _mround(x, multiple):
    if multiple == 0:
        return 0
    return round(x / multiple) * multiple


def calcular_edad(data: dict) -> int:
    fn = _to_date(data['fechaNacimiento'])
    return relativedelta(datetime.date.today(), fn).years


def calcular_antiguedadFondo(data: dict) -> float:
    fi = _to_date(data['fechaIngreso'])
    return float(relativedelta(datetime.date.today(), fi).years)


def calcular_aportesAhorros(data: dict) -> float:
    return data['aportes'] + data['ahorrosFondo']


def calcular_tasausuraper(data: dict) -> float:
    return (1 + data['tasaUsura']) ** (1 / 12) - 1


def calcular_VALOR_DESPROTEGIDO_MAX_DE_LA_LINEA(data: dict, resultados: dict):
    afianzado = data['creditoAfianzado']
    perfil = resultados['PERFIL']
    ingresos = resultados['Ingresos']

    if afianzado == 1:
        if perfil == "A":
            return 24512670
        if perfil == "B":
            return 17509050
        return False

    if perfil == "A" and 17509050 <= ingresos <= 3501810:
        return 8754525
    if perfil == "B" and 17509050 <= ingresos <= 3501810:
        return 7003620
    if perfil == "C" and 17509050 <= ingresos <= 3501810:
        return 3501810

    if perfil == "A" and 3501811 <= ingresos <= 7003620:
        return 14007240
    if perfil == "B" and 3501811 <= ingresos <= 7003620:
        return 8754525
    if perfil == "C" and 3501811 <= ingresos <= 7003620:
        return 3501810

    if perfil == "A" and ingresos >= 7003621:
        return 19259955
    if perfil == "B" and ingresos >= 7003621:
        return 10505430
    if perfil == "C" and ingresos >= 7003621:
        return 3501810

    return False


def calcular_Cuota_TDC(data: dict, resultados: dict) -> float:
    return float(npf.pmt(data['tasausuraper'], data['plazoTarjetas'], -data['cuposTdc']))


def calcular_Descuentos_de_Ley(data: dict, resultados: dict) -> float:
    tipo = data['tipoSalario']
    sal = data['salario']
    if tipo == "Normal" and sal > 7003620:
        return sal * 0.09
    if tipo == "Normal" and sal <= 7003620:
        return sal * 0.08
    if tipo == "Integral" and sal > 7003620:
        return (sal * 0.70) * 0.09
    if tipo == "Integral" and sal <= 7003620:
        return (sal * 0.70) * 0.08
    if tipo == "Pensionado":
        return sal * 0.12
    return 0


def calcular_Frecuencia_mes(data: dict, resultados: dict):
    f = data['frecuenciaPagos']
    if f == "semanal":
        return 4
    if f == "quincenal":
        return 2
    if f == "mensual":
        return 1
    return "Revisar"


def calcular_Ingresos(data: dict, resultados: dict) -> int:
    return data['salario']


def calcular_Minimo_Vital(data: dict, resultados: dict) -> float:
    sal = data['salario']
    if 1750905 <= sal <= 7003620:
        return sal * 0.50
    if 7003620 < sal <= 17509050:
        return sal * 0.40
    if sal > 17509050:
        return sal * 0.30
    return 0


def calcular_Egresos(data: dict, resultados: dict) -> float:
    return (data['egresosVolante'] + data['egresosSector']
            + resultados['Cuota TDC']
            - data['cuotarecogeCoopvalili']
            - data['cuotarecogeSector'])


def calcular_Cuota_Max_Endeu_Mensual(data: dict, resultados: dict) -> float:
    return data['salario'] * 0.5 - data['egresosVolante']


def calcular_Cuota_Max_Endeu_Periodica(data: dict, resultados: dict) -> float:
    return resultados['Cuota Máximo por Endeudamiento Mensual'] / resultados['Frecuencia mes']


def calcular_Cuota_Max_Capacidad_Mensual(data: dict, resultados: dict) -> float:
    return max(0, resultados['Ingresos'] - resultados['Mínimo Vital'] - resultados['Egresos'])


def calcular_Cuota_Max_Capacidad_Periodica(data: dict, resultados: dict) -> float:
    return resultados['Cuota Máxima por Capacidad Mensual'] / resultados['Frecuencia mes']


def calcular_Cuota_Max_Capacidad(data: dict, resultados: dict) -> float:
    return min(resultados['Cuota Máxima por Capacidad Periódica'],
               resultados['Cuota Máximo por Endeudamiento Periódica'])


def calcular_Maximo_Deuda_por_Endeudamiento(data: dict, resultados: dict):
    c15 = resultados['Cuota Máxima por Capacidad']
    c22 = resultados['N° de Periodos (n)']
    c23 = resultados['tasa_per']
    if c15 <= 0:
        return "Revisar"
    try:
        val = c15 * ((1 - (1 + c23) ** -c22) / c23)
        return _floor_to(val, 100000)
    except Exception:
        return 0


def calcular_Total_Ahorros_Prestaciones(data: dict, resultados: dict) -> float:
    return data['aportesAhorros']


def calcular_Maximo_Deuda_Desprotegido(data: dict, resultados: dict) -> float:
    return _floor_to(resultados['Total Ahorros+Prestaciones']
                     + resultados['VALOR DESPROTEGIDO MAX DE LA LINEA']
                     - data['deudaCoopvalili'], 100000)


def calcular_Valor_Final_Credito_Motor(data: dict, resultados: dict) -> float:
    return min(resultados['Maximo Deuda por Endeudamiento'],
               resultados['Maximo Deuda por Desprotegido'])


def calcular_Tasa_Interes_Efectiva(data: dict, resultados: dict) -> float:
    return 0.3015


def calcular_tasa_namv(data: dict, resultados: dict) -> float:
    eff = resultados['Tasa Interés Efectiva']
    nper = resultados['N° de Periodos (n)']
    return nper * ((1 + eff) ** (1 / nper) - 1)


def calcular_N_Periodos(data: dict, resultados: dict):
    f = data['frecuenciaPagos']
    if f.lower() == "mensual":
        return 12
    if f.lower() == "quincenal":
        return 24
    if f.lower() == "semanal":
        return 52
    return ""


def calcular_tasa_per(data: dict, resultados: dict) -> float:
    return resultados['tasa_namv'] / resultados['N° de Periodos (n)']


def calcular_Cuota_Periodica_Solicitada(data: dict, resultados: dict) -> int:
    return int(npf.pmt(resultados['tasa_per'], resultados['N° de Periodos (n)'], -data['montoSolicitado']))


def calcular_Regla1(data: dict, resultados: dict) -> int:
    return 1 if resultados['Valor Final del Crédito por Motor'] >= data['montoSolicitado'] else 0


def calcular_Regla2(data: dict, resultados: dict) -> int:
    return 1 if (resultados['Valor Final del Crédito por Motor'] >= data['parametroCredito']
                 and resultados['Regla 1 monto_motor > = monto_solicitud'] == 0) else 0


def calcular_Regla3(data: dict, resultados: dict) -> int:
    return 1 if (data['parametroCredito'] > resultados['Valor Final del Crédito por Motor']
                 and resultados['Regla 1 monto_motor > = monto_solicitud'] == 0
                 and resultados['Regla 2 monto_motor > = param'] == 0) else 0


def calcular_Monto_definitivo(data: dict, resultados: dict):
    r1 = resultados['Regla 1 monto_motor > = monto_solicitud']
    r2 = resultados['Regla 2 monto_motor > = param']
    r3 = resultados['Regla 3 param > = monto_motor']
    if r1 == 1:
        return resultados['Valor Final del Crédito por Motor']
    if r2 == 1:
        return resultados['Valor Final del Crédito por Motor']
    if r3 == 1:
        return 0
    return "Revisar"


def calcular_Cuota_definitiva(data: dict, resultados: dict):
    monto = resultados['Monto definitivo']
    if not isinstance(monto, (int, float)):
        return "Revisar"
    return int(npf.pmt(resultados['tasa_per'], resultados['N° de Periodos (n)'], -monto))


def calcular_Concepto_definitivo(data: dict, resultados: dict) -> str:
    r1 = resultados['Regla 1 monto_motor > = monto_solicitud']
    r2 = resultados['Regla 2 monto_motor > = param']
    r3 = resultados['Regla 3 param > = monto_motor']
    if r1 == 1:
        return "Preaprobado"
    if r2 == 1:
        return "Preaprobado"
    if r3 == 1:
        return "No viable"
    return "Revisar"


def calcular_Endeudamiento_Actual(data: dict, resultados: dict):
    try:
        return _mround(data['egresosVolante'] / resultados['Resumen Salarial del Asociado'], 0.01)
    except Exception:
        return ""


def calcular_Endeudamiento_Actual_Cupo(data: dict, resultados: dict):
    try:
        return _mround(data['egresosVolante'] / resultados['Resumen Salarial del Asociado'], 0.01)
    except Exception:
        return ""


def calcular_Endeudamiento_Proyectado(data: dict, resultados: dict):
    try:
        return (
            data['egresosVolante']
            + resultados['Cuota definitiva']
            - data['cuotarecogeCoopvalili']
        ) / resultados['Resumen Salarial del Asociado']
    except Exception:
        return 0


def calcular_Endeudamiento_Proyectado_Cupo(data: dict, resultados: dict):
    try:
        return _mround((data['egresosVolante'] + resultados['Cuota definitiva']
                        - data['cuotarecogeCoopvalili']) / resultados['Resumen Salarial del Asociado'], 0.01)
    except Exception:
        return ""


def calcular_Maximo_Endeudamiento(data: dict, resultados: dict) -> float:
    return 0.5


def calcular_cumple_end(data: dict, resultados: dict) -> int:
    return 1 if resultados['Endeudamiento Proyectado'] <= resultados['Máximo Endeudamiento'] else 0


def calcular_Solvencia(data: dict, resultados: dict):
    try:
        return (
            resultados['Egresos']
            + resultados['Cuota definitiva']
        ) / data['salario']
    except Exception:
        return 0


def calcular_cumple_sol(data: dict, resultados: dict) -> int:
    return 1 if resultados['Solvencia'] <= 1 else 0


def calcular_Disponible(data: dict, resultados: dict) -> int:
    return int(resultados['Ingresos'] - resultados['Mínimo Vital'] - resultados['Egresos'] - resultados['Cuota definitiva'])


def calcular_cumple_disp(data: dict, resultados: dict) -> int:
    return 1 if resultados['Disponible'] > 10000 else 0


def calcular_Desprotegido_Maximo(data: dict, resultados: dict):
    return resultados['VALOR DESPROTEGIDO MAX DE LA LINEA']


def calcular_Desprotegido(data: dict, resultados: dict) -> int:
    return int(-resultados['Total Ahorros+Prestaciones'] + resultados['Monto definitivo'] + data['deudaCoopvalili'])


def calcular_cumple_des(data: dict, resultados: dict) -> int:
    return 1 if resultados['Desprotegido'] <= resultados['Desprotegido Máximo'] else 0


def calcular_Cumplimiento_4_criterios(data: dict, resultados: dict) -> int:
    return 1 if (resultados['cumple_end'] + resultados['cumple_sol']
                 + resultados['cumple_disp'] + resultados['cumple_des']) == 4 else 0


def calcular_USARIO_CREDITO(data: dict, resultados: dict):
    d = data['deudaCoopvalili']
    if d == "" or d is None:
        return ""
    if d <= 1000000:
        return 0
    if d <= 5000000:
        return 1
    if d <= 10000000:
        return 3
    if d > 10000000:
        return 6
    return "Revisar"


def calcular_SCOR_NIVEL_RIESGO(data: dict, resultados: dict):
    s = data['scoreCifin']
    if s <= 200:
        return 0
    if s <= 500:
        return 1
    if s <= 795:
        return 2
    if s <= 1000:
        return 7
    return 0


def calcular_SCOR_EDAD(data: dict, resultados: dict):
    e = data['edad']
    if e == "" or e is None:
        return ""
    if e <= 25:
        return 2
    if e <= 45:
        return 4
    if e <= 60:
        return 3
    return 1


def calcular_SCOR_PCARGO(data: dict, resultados: dict):
    p = data['personasCargo']
    if p == "" or p is None:
        return ""
    if p <= 1:
        return 5
    if p <= 3:
        return 3
    if p <= 4:
        return 2
    return 0


def calcular_SCOR_VIVIENDA(data: dict, resultados: dict):
    v = data['tipoVivienda']
    if v == "" or v is None:
        return ""
    if v == 1:
        return 6
    if v == 3:
        return 4
    return 0


def calcular_SCOR_ANT_COOP(data: dict, resultados: dict):
    a = data['antiguedadFondo']
    if a == "" or a is None:
        return ""
    if a <= 1:
        return 1
    if a <= 5:
        return 2
    if a <= 10:
        return 3
    return 4


def calcular_SCOR_ANT_LABORAL(data: dict, resultados: dict):
    a = data['antiguedadLaboral']
    if a == "" or a is None:
        return ""
    if a <= 1:
        return 1
    if a <= 5:
        return 2
    if a <= 10:
        return 3
    return 4


def calcular_SCOR_INGRESOS(data: dict, resultados: dict):
    s = data['salario']
    if s <= 2600000:
        return 1
    if s <= 6500000:
        return 2
    if s <= 13000000:
        return 3
    return 4


def calcular_TOTALES_SCOR(data: dict, resultados: dict) -> float:
    return round(
        resultados['USARIO_CREDITO'] * 0.2
        + resultados['SCOR_NIVEL_RIESGO'] * 0.3
        + resultados['SCOR_EDAD'] * 0.05
        + resultados['SCOR_PCARGO'] * 0.05
        + resultados['SCOR_VIVIENDA'] * 0.1
        + resultados['SCOR_ANT_COOP'] * 0.15
        + resultados['SCOR_ANT_LABORAL'] * 0.1
        + resultados['SCOR_INGRESOS'] * 0.05,
        2,
    )


def calcular_PERFIL(data: dict, resultados: dict) -> str:
    c53 = resultados['TOTALES_SCOR']
    try:
        if c53 >= 4.01:
            return "A"
        if c53 >= 2.7:
            return "B"
        if c53 >= 0:
            return "C"
        return "Retirado"
    except Exception:
        return "Retirado"


def calcular_Resumen_Salarial(data: dict, resultados: dict) -> int:
    sal = data['salario']
    tipo = data['tipoSalario']
    base = sal * 0.70 if tipo == "Integral" else sal
    pct = 0.09 if sal > (1750905 * 4) else 0.08
    return int(sal - base * pct)


def calcular_VIABLE_CMD(data: dict, resultados: dict):
    try:
        return _mround((resultados['Cuota definitiva'] + data['egresosVolante'] - data['cuotarecogeCoopvalili'])
                       / resultados['Resumen Salarial del Asociado'], 0.01)
    except Exception:
        return ""


# Bloque 1
def calcular_Egresos_volante_ajustado_1(data: dict, resultados: dict) -> float:
    if data['cuotarecogeCoopvalili'] > data['egresosVolante']:
        return data['cuotarecogeCoopvalili'] + data['aporteMensual']
    return data['egresosVolante']


def calcular_Total_egresos_1(data: dict, resultados: dict) -> float:
    return (resultados['Egresos volante ajustado_1'] + resultados['Mínimo Vital']
            + resultados['Cuota TDC'] + resultados['Descuentos de Ley']
            + data['cuotarecogeSector'])


def calcular_Capacidad_de_pago_1(data: dict, resultados: dict) -> float:
    return resultados['Ingresos'] - resultados['Total egresos_1']


def calcular_Monto_credito_1_pre(data: dict, resultados: dict) -> float:
    c23 = resultados['tasa_per']
    c22 = resultados['N° de Periodos (n)']
    c57 = resultados['Capacidad de pago_1']
    try:
        val = c57 * ((1 - (1 + c23) ** -c22) / c23)
        return _floor_to(val, 100000)
    except Exception:
        return 0


def calcular_monto_min_1(data: dict, resultados: dict) -> float:
    return 1000000


def calcular_monto_max_1(data: dict, resultados: dict) -> float:
    return 7000000


def calcular_Monto_credito_1(data: dict, resultados: dict) -> float:
    c58 = resultados['Monto credito_1_pre']
    c59 = resultados['monto min_1']
    c60 = resultados['monto max_1']
    if c58 < c59:
        return 0
    if c58 > c60:
        return c60
    return c58


def calcular_Endeudamiento_Proyectado_1(data: dict, resultados: dict):
    try:
        return (
            resultados['Egresos volante ajustado_1']
            + resultados['Capacidad de pago_1']
        ) / resultados['Resumen Salarial del Asociado']
    except Exception:
        return 0


def calcular_cumple_end_1(data: dict, resultados: dict) -> int:
    return 1 if resultados['Endeudamiento Proyectado_b1'] <= resultados['Máximo Endeudamiento'] else 0


def calcular_Solvencia_1(data: dict, resultados: dict):
    try:
        return (
            resultados['Total egresos_1']
            + resultados['Capacidad de pago_1']
        ) / data['salario']
    except Exception:
        return 0


def calcular_cumple_sol_1(data: dict, resultados: dict) -> int:
    return 1 if resultados['Solvencia_b1'] <= 1 else 0


def calcular_cumple_disp_1(data: dict, resultados: dict) -> int:
    return 1 if resultados['Capacidad de pago_1'] > 10000 else 0


def calcular_desprotegido_1(data: dict, resultados: dict) -> float:
    return resultados['Monto credito_1'] + data['deudaCoopvalili'] - resultados['Total Ahorros+Prestaciones']


def calcular_cumple_des_1(data: dict, resultados: dict) -> int:
    return 1 if resultados['desprotegido_b1'] <= resultados['Desprotegido Máximo'] else 0


def calcular_Cumple_4_criterios_1(data: dict, resultados: dict) -> int:
    return 1 if (resultados['cumple_end_b1'] + resultados['cumple_sol_b1']
                 + resultados['cumple_disp_b1'] + resultados['cumple_des_b1']) == 4 else 0


# Bloque 2
def calcular_Total_egresos_2(data: dict, resultados: dict) -> float:
    return (resultados['Egresos volante ajustado_1'] + resultados['Mínimo Vital']
            + resultados['Cuota TDC'] + resultados['Descuentos de Ley']
            - data['cuotarecogeCoopvalili'] + data['cuotarecogeSector'])


def calcular_Capacidad_de_pago_2(data: dict, resultados: dict) -> float:
    return resultados['Ingresos'] - resultados['Total egresos_2']


def calcular_Monto_credito_2_pre(data: dict, resultados: dict) -> float:
    c23 = resultados['tasa_per']
    c22 = resultados['N° de Periodos (n)']
    c71 = resultados['Capacidad de pago_2']
    try:
        val = c71 * ((1 - (1 + c23) ** -c22) / c23)
        return _floor_to(val, 100000)
    except Exception:
        return 0


def calcular_monto_min_2(data: dict, resultados: dict) -> float:
    return 2000000


def calcular_monto_max_2(data: dict, resultados: dict) -> float:
    return 17000000


def calcular_Monto_credito_2(data: dict, resultados: dict) -> float:
    c72 = resultados['Monto credito_2_pre']
    c73 = resultados['monto min_2']
    c74 = resultados['monto max_2']
    d10 = data['deudaCoopvalili']
    if c72 < c73:
        return 0
    if c72 > c74 and c74 > d10:
        return c74
    if c72 > d10 and c72 <= c74 and c72 >= c73:
        return c72
    return 0


def calcular_Endeudamiento_Proyectado_2(data: dict, resultados: dict):
    try:
        return (
            resultados['Egresos volante ajustado_1']
            + resultados['Capacidad de pago_2']
        ) / resultados['Resumen Salarial del Asociado']
    except Exception:
        return 0


def calcular_cumple_end_2(data: dict, resultados: dict) -> int:
    return 1 if resultados['Endeudamiento Proyectado_b2'] <= resultados['Máximo Endeudamiento'] else 0


def calcular_Solvencia_2(data: dict, resultados: dict):
    try:
        return (
            resultados['Total egresos_2']
            + resultados['Capacidad de pago_2']
        ) / data['salario']
    except Exception:
        return 0


def calcular_cumple_sol_2(data: dict, resultados: dict) -> int:
    return 1 if resultados['Solvencia_b2'] <= 1 else 0


def calcular_cumple_disp_2(data: dict, resultados: dict) -> int:
    return 1 if resultados['Capacidad de pago_2'] > 10000 else 0


def calcular_desprotegido_2(data: dict, resultados: dict) -> float:
    return resultados['Monto credito_2'] + data['deudaCoopvalili'] - resultados['Total Ahorros+Prestaciones']


def calcular_cumple_des_2(data: dict, resultados: dict) -> int:
    return 1 if resultados['desprotegido_b2'] <= resultados['Desprotegido Máximo'] else 0


def calcular_Cumple_4_criterios_2(data: dict, resultados: dict) -> int:
    return 1 if (resultados['cumple_end_b2'] + resultados['cumple_sol_b2']
                 + resultados['cumple_disp_b2'] + resultados['cumple_des_b2']) == 4 else 0


# Bloque 3
def calcular_Total_egresos_3(data: dict, resultados: dict) -> float:
    return (resultados['Egresos volante ajustado_1'] + resultados['Descuentos de Ley']
            + resultados['Mínimo Vital'] + resultados['Cuota TDC']
            - data['cuotarecogeCoopvalili'])


def calcular_Capacidad_de_pago_3(data: dict, resultados: dict) -> float:
    return resultados['Ingresos'] - resultados['Total egresos_3']


def calcular_Monto_credito_3_pre(data: dict, resultados: dict) -> float:
    c23 = resultados['tasa_per']
    c22 = resultados['N° de Periodos (n)']
    c85 = resultados['Capacidad de pago_3']
    try:
        val = c85 * ((1 - (1 + c23) ** -c22) / c23)
        return _floor_to(val, 100000)
    except Exception:
        return 0


def calcular_monto_min_3(data: dict, resultados: dict) -> float:
    return 3000000


def calcular_monto_max_3(data: dict, resultados: dict) -> float:
    return 16000000


def calcular_Monto_credito_3(data: dict, resultados: dict) -> float:
    c86 = resultados['Monto credito_3_pre']
    c87 = resultados['monto min_3']
    c88 = resultados['monto max_3']
    d11 = data.get('deudaSector') or 0
    if c86 < c87:
        return 0
    if c86 > c88 and c88 > d11:
        return c88
    if c86 > d11 and c86 <= c88 and c86 >= c87:
        return c86
    return 0


def calcular_Endeudamiento_Proyectado_3(data: dict, resultados: dict):
    try:
        return (
            resultados['Egresos volante ajustado_1']
            + resultados['Capacidad de pago_3']
        ) / resultados['Resumen Salarial del Asociado']
    except Exception:
        return 0


def calcular_cumple_end_3(data: dict, resultados: dict) -> int:
    return 1 if resultados['Endeudamiento Proyectado_b3'] <= resultados['Máximo Endeudamiento'] else 0


def calcular_Solvencia_3(data: dict, resultados: dict):
    try:
        return (
            resultados['Total egresos_3']
            + resultados['Capacidad de pago_3']
        ) / data['salario']
    except Exception:
        return 0


def calcular_cumple_sol_3(data: dict, resultados: dict) -> int:
    return 1 if resultados['Solvencia_b3'] <= 1 else 0


def calcular_cumple_disp_3(data: dict, resultados: dict) -> int:
    return 1 if resultados['Capacidad de pago_3'] > 10000 else 0


def calcular_desprotegido_3(data: dict, resultados: dict) -> float:
    return resultados['Monto credito_3'] + data['deudaCoopvalili'] - resultados['Total Ahorros+Prestaciones']


def calcular_cumple_des_3(data: dict, resultados: dict) -> int:
    return 1 if resultados['desprotegido_b3'] <= resultados['Desprotegido Máximo'] else 0


def calcular_Cumple_4_criterios_3(data: dict, resultados: dict) -> int:
    return 1 if (resultados['cumple_end_b3'] + resultados['cumple_sol_b3']
                 + resultados['cumple_disp_b3'] + resultados['cumple_des_b3']) == 4 else 0


def procesar_credito(data: dict) -> dict:
    """Recibe el detallado_want y devuelve los resultados del processing."""

    data['edad'] = calcular_edad(data)
    data['antiguedadFondo'] = calcular_antiguedadFondo(data)
    data['aportesAhorros'] = calcular_aportesAhorros(data)
    data['tasausuraper'] = calcular_tasausuraper(data)

    resultados: dict = {}

    # Constantes / parámetros
    resultados['Tasa Interés Efectiva'] = calcular_Tasa_Interes_Efectiva(
        data, resultados)
    resultados['Máximo Endeudamiento'] = calcular_Maximo_Endeudamiento(
        data, resultados)
    resultados['monto min_1'] = calcular_monto_min_1(data, resultados)
    resultados['monto max_1'] = calcular_monto_max_1(data, resultados)
    resultados['monto min_2'] = calcular_monto_min_2(data, resultados)
    resultados['monto max_2'] = calcular_monto_max_2(data, resultados)
    resultados['monto min_3'] = calcular_monto_min_3(data, resultados)
    resultados['monto max_3'] = calcular_monto_max_3(data, resultados)

    # Scores base
    resultados['Ingresos'] = calcular_Ingresos(data, resultados)
    resultados['Frecuencia mes'] = calcular_Frecuencia_mes(data, resultados)
    resultados['N° de Periodos (n)'] = calcular_N_Periodos(data, resultados)
    resultados['tasa_namv'] = calcular_tasa_namv(data, resultados)
    resultados['tasa_per'] = calcular_tasa_per(data, resultados)

    resultados['Cuota TDC'] = calcular_Cuota_TDC(data, resultados)
    resultados['Descuentos de Ley'] = calcular_Descuentos_de_Ley(
        data, resultados)
    resultados['Mínimo Vital'] = calcular_Minimo_Vital(data, resultados)
    resultados['Egresos'] = calcular_Egresos(data, resultados)

    # Scores
    resultados['USARIO_CREDITO'] = calcular_USARIO_CREDITO(data, resultados)
    resultados['SCOR_NIVEL_RIESGO'] = calcular_SCOR_NIVEL_RIESGO(
        data, resultados)
    resultados['SCOR_EDAD'] = calcular_SCOR_EDAD(data, resultados)
    resultados['SCOR_PCARGO'] = calcular_SCOR_PCARGO(data, resultados)
    resultados['SCOR_VIVIENDA'] = calcular_SCOR_VIVIENDA(data, resultados)
    resultados['SCOR_ANT_COOP'] = calcular_SCOR_ANT_COOP(data, resultados)
    resultados['SCOR_ANT_LABORAL'] = calcular_SCOR_ANT_LABORAL(
        data, resultados)
    resultados['SCOR_INGRESOS'] = calcular_SCOR_INGRESOS(data, resultados)
    resultados['TOTALES_SCOR'] = calcular_TOTALES_SCOR(data, resultados)
    resultados['PERFIL'] = calcular_PERFIL(data, resultados)
    resultados['Resumen Salarial del Asociado'] = calcular_Resumen_Salarial(
        data, resultados)

    # Desprotegido y deuda máxima
    resultados['VALOR DESPROTEGIDO MAX DE LA LINEA'] = calcular_VALOR_DESPROTEGIDO_MAX_DE_LA_LINEA(
        data, resultados)
    resultados['Total Ahorros+Prestaciones'] = calcular_Total_Ahorros_Prestaciones(
        data, resultados)

    # Cuotas máximas
    resultados['Cuota Máximo por Endeudamiento Mensual'] = calcular_Cuota_Max_Endeu_Mensual(
        data, resultados)
    resultados['Cuota Máximo por Endeudamiento Periódica'] = calcular_Cuota_Max_Endeu_Periodica(
        data, resultados)
    resultados['Cuota Máxima por Capacidad Mensual'] = calcular_Cuota_Max_Capacidad_Mensual(
        data, resultados)
    resultados['Cuota Máxima por Capacidad Periódica'] = calcular_Cuota_Max_Capacidad_Periodica(
        data, resultados)
    resultados['Cuota Máxima por Capacidad'] = calcular_Cuota_Max_Capacidad(
        data, resultados)

    resultados['Maximo Deuda por Endeudamiento'] = calcular_Maximo_Deuda_por_Endeudamiento(
        data, resultados)
    resultados['Maximo Deuda por Desprotegido'] = calcular_Maximo_Deuda_Desprotegido(
        data, resultados)
    resultados['Valor Final del Crédito por Motor'] = calcular_Valor_Final_Credito_Motor(
        data, resultados)

    # Solicitada y reglas
    resultados['Cuota Periodica Solicitada'] = calcular_Cuota_Periodica_Solicitada(
        data, resultados)
    resultados['Regla 1 monto_motor > = monto_solicitud'] = calcular_Regla1(
        data, resultados)
    resultados['Regla 2 monto_motor > = param'] = calcular_Regla2(
        data, resultados)
    resultados['Regla 3 param > = monto_motor'] = calcular_Regla3(
        data, resultados)
    resultados['Monto definitivo'] = calcular_Monto_definitivo(
        data, resultados)
    resultados['Cuota definitiva'] = calcular_Cuota_definitiva(
        data, resultados)
    resultados['Concepto definitivo'] = calcular_Concepto_definitivo(
        data, resultados)

    # Endeudamientos
    resultados['Endeudamiento Actual'] = calcular_Endeudamiento_Actual(
        data, resultados)
    resultados['Endeudamiento Actual con Cupo Coopvalili'] = calcular_Endeudamiento_Actual_Cupo(
        data, resultados)
    resultados['Endeudamiento Proyectado'] = calcular_Endeudamiento_Proyectado(
        data, resultados)
    resultados['Endeudamiento Proyectado Con Cupo Coopvalili'] = calcular_Endeudamiento_Proyectado_Cupo(
        data, resultados)

    resultados['cumple_end'] = calcular_cumple_end(data, resultados)
    resultados['Solvencia'] = calcular_Solvencia(data, resultados)
    resultados['cumple_sol'] = calcular_cumple_sol(data, resultados)
    resultados['Disponible'] = calcular_Disponible(data, resultados)
    resultados['cumple_disp'] = calcular_cumple_disp(data, resultados)
    resultados['Desprotegido Máximo'] = calcular_Desprotegido_Maximo(
        data, resultados)
    resultados['Desprotegido'] = calcular_Desprotegido(data, resultados)
    resultados['cumple_des'] = calcular_cumple_des(data, resultados)
    resultados['Cumplimiento 4 criterios'] = calcular_Cumplimiento_4_criterios(
        data, resultados)
    resultados['VIABLE  CMD'] = calcular_VIABLE_CMD(data, resultados)

    # Bloque 1
    resultados['Egresos volante ajustado_1'] = calcular_Egresos_volante_ajustado_1(
        data, resultados)
    resultados['Total egresos_1'] = calcular_Total_egresos_1(data, resultados)
    resultados['Capacidad de pago_1'] = calcular_Capacidad_de_pago_1(
        data, resultados)
    resultados['Monto credito_1_pre'] = calcular_Monto_credito_1_pre(
        data, resultados)
    resultados['Monto credito_1'] = calcular_Monto_credito_1(data, resultados)
    resultados['Endeudamiento Proyectado_b1'] = calcular_Endeudamiento_Proyectado_1(
        data, resultados)
    resultados['cumple_end_b1'] = calcular_cumple_end_1(data, resultados)
    resultados['Solvencia_b1'] = calcular_Solvencia_1(data, resultados)
    resultados['cumple_sol_b1'] = calcular_cumple_sol_1(data, resultados)
    resultados['cumple_disp_b1'] = calcular_cumple_disp_1(data, resultados)
    resultados['desprotegido_b1'] = calcular_desprotegido_1(data, resultados)
    resultados['cumple_des_b1'] = calcular_cumple_des_1(data, resultados)
    resultados['Cumple 4 criterios_b1'] = calcular_Cumple_4_criterios_1(
        data, resultados)

    # Bloque 2
    resultados['Total egresos_2'] = calcular_Total_egresos_2(data, resultados)
    resultados['Capacidad de pago_2'] = calcular_Capacidad_de_pago_2(
        data, resultados)
    resultados['Monto credito_2_pre'] = calcular_Monto_credito_2_pre(
        data, resultados)
    resultados['Monto credito_2'] = calcular_Monto_credito_2(data, resultados)
    resultados['Endeudamiento Proyectado_b2'] = calcular_Endeudamiento_Proyectado_2(
        data, resultados)
    resultados['cumple_end_b2'] = calcular_cumple_end_2(data, resultados)
    resultados['Solvencia_b2'] = calcular_Solvencia_2(data, resultados)
    resultados['cumple_sol_b2'] = calcular_cumple_sol_2(data, resultados)
    resultados['cumple_disp_b2'] = calcular_cumple_disp_2(data, resultados)
    resultados['desprotegido_b2'] = calcular_desprotegido_2(data, resultados)
    resultados['cumple_des_b2'] = calcular_cumple_des_2(data, resultados)
    resultados['Cumple 4 criterios_b2'] = calcular_Cumple_4_criterios_2(
        data, resultados)

    # Bloque 3
    resultados['Total egresos_3'] = calcular_Total_egresos_3(data, resultados)
    resultados['Capacidad de pago_3'] = calcular_Capacidad_de_pago_3(
        data, resultados)
    resultados['Monto credito_3_pre'] = calcular_Monto_credito_3_pre(
        data, resultados)
    resultados['Monto credito_3'] = calcular_Monto_credito_3(data, resultados)
    resultados['Endeudamiento Proyectado_b3'] = calcular_Endeudamiento_Proyectado_3(
        data, resultados)
    resultados['cumple_end_b3'] = calcular_cumple_end_3(data, resultados)
    resultados['Solvencia_b3'] = calcular_Solvencia_3(data, resultados)
    resultados['cumple_sol_b3'] = calcular_cumple_sol_3(data, resultados)
    resultados['cumple_disp_b3'] = calcular_cumple_disp_3(data, resultados)
    resultados['desprotegido_b3'] = calcular_desprotegido_3(data, resultados)
    resultados['cumple_des_b3'] = calcular_cumple_des_3(data, resultados)
    resultados['Cumple 4 criterios_b3'] = calcular_Cumple_4_criterios_3(
        data, resultados)
    
    campos_porcentaje = [
        'Endeudamiento Proyectado_b1',
        'Solvencia_b1',

        'Endeudamiento Proyectado_b2',
        'Solvencia_b2',

        'Endeudamiento Proyectado_b3',
        'Solvencia_b3',

    ]

    for campo in campos_porcentaje:
        valor = resultados.get(campo)

        if isinstance(valor, (int, float)):
            resultados[campo] = f"{round(valor * 100, 2):.2f}%"

    return resultados


def procesar_solicitud(payload: dict) -> dict[str, Any]:
    detallado = payload.get("detallado_want")

    if not isinstance(detallado, dict):
        return {
            "status": "error",
            "radicado": None,
            "processing": None,
            "meta": {"mensaje": "Campo 'detallado_want' requerido en el body"},
        }

    radicado = detallado.get("radicado")

    try:
        resultados = procesar_credito(dict(detallado))
        return {
            "status": "ok",
            "radicado": radicado,
            "processing": resultados,
            "meta": {"mensaje": "Procesamiento completado correctamente"},
        }
    except Exception as exc:
        log.error("error en procesar_credito", extra={"error": str(exc)})
        return {
            "status": "error",
            "radicado": radicado,
            "processing": None,
            "meta": {"mensaje": f"Error en cálculos: {str(exc)[:200]}"},
        }


def main(req: func.HttpRequest) -> func.HttpResponse:
    log.info("request recibido", extra={"endpoint": "/api/motor_process"})

    # Auth
    try:
        validar_api_key(req.headers.get("x-api-key"))
    except AuthError as exc:
        log.warning("auth fallida", extra={"reason": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": str(exc), "code": exc.code}),
            status_code=401,
            mimetype="application/json",
        )

    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body JSON inválido"}),
            status_code=400,
            mimetype="application/json",
        )

    try:
        salida = procesar_solicitud(payload)
    except Exception as exc:
        log.error("error en procesar_solicitud", extra={"error": str(exc)})
        return func.HttpResponse(
            json.dumps({"error": "Error interno del servidor"}),
            status_code=500,
            mimetype="application/json",
        )

    detallado_in = payload.get("detallado_want") or {}
    cedula = str(detallado_in.get("id") or "sin_cedula")
    radicado = salida.get("radicado")

    try:
        save_motor_process_supabase(radicado, cedula, salida)
        salida["_supabase_save"] = "OK"
    except Exception as exc:
        log.warning("fallo supabase motor_process",
                    extra={"cedula": cedula, "error": str(exc)})
        salida["_supabase_save"] = f"ERROR: {str(exc)[:200]}"

    try:
        save_json_blob_by_id(cedula, "motor_process_output.json", salida)
        salida["_blob_save"] = "OK"
        log.info("blob guardado", extra={"cedula": cedula})
    except Exception as exc:
        log.warning("fallo blob", extra={"cedula": cedula, "error": str(exc)})
        salida["_blob_save"] = f"ERROR: {str(exc)[:200]}"

    return func.HttpResponse(
        json.dumps(salida, ensure_ascii=False, default=str),
        status_code=200,
        mimetype="application/json",
    )
