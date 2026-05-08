import json
import os
from collections import defaultdict
import uuid
from datetime import datetime, timezone, timedelta
def _pmt(rate, nper, pv):
    if rate == 0:
        return -pv / nper
    return (pv * rate * (1 + rate) ** nper) / (1 - (1 + rate) ** nper)

class _npf:
    @staticmethod
    def pmt(rate, nper, pv):
        return _pmt(rate, nper, pv)
npf = _npf()
import math
import requests
import re
import unicodedata
from .blob_loader import save_json_blob_by_id
from .proxy_request import proxy_request


base_path = r"C:/Want/Motores/Coprocenva/s1"

# ============================================================
# Helpers: normalización y extracción de payload COPRO
# ============================================================
def _extraer_payload_copro(obj):
    """
    Acepta:
      - dict plano
      - lista con 1+ dicts: [ {...} ]
      - envolturas comunes: {"data": {...}}, {"result": {...}}, {"response": {...}}
    y devuelve siempre un dict.
    """
    if obj is None:
        return {}
    if isinstance(obj, list):
        return obj[0] if obj else {}
    if isinstance(obj, dict):
        for key in ("data", "result", "response", "payload"):
            val = obj.get(key)
            if isinstance(val, dict):
                return val
            if isinstance(val, list) and val:
                return val[0]
        return obj
    return {}

def _norm_texto(s: str) -> str:
    """Normaliza texto: trim, lower, sin tildes, espacios colapsados."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", s)
        if unicodedata.category(ch) != "Mn"
    )
    s = re.sub(r"\s+", " ", s)
    return s
def _to_float_money(x):
    """Convierte valores tipo dinero a float: soporta int/float y strings con $ . , espacios."""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    try:
        s = str(x).strip()
        if not s:
            return 0.0
        s = s.replace("$", "").replace("COP", "").replace(" ", "")
        s = s.replace(".", "").replace(",", "")
        return float(s) if s else 0.0
    except Exception:
        return 0.0

# ============================================================
# PASO 0 – Lectura de entrada y configuración base
# ============================================================

def paso0_leer_input_y_decidir(payload):

    # =====================================
    # PASO 0.1 – Lectura del Chat Input   
    # =====================================
    # chat_input_file = os.path.join(base_path, "Chat_Input.json")

    # with open(chat_input_file, "r", encoding="utf-8") as f:
    #     chat_input = json.load(f)

    chat_input = payload

    process_type = int(chat_input.get("process_type", 1))
    if process_type not in (1, 2):
        raise ValueError(f"process_type inválido en Chat_Input.json: {process_type}")

    # =====================================
    # PASO 0.2 – Definición de rutas y archivos auxiliares
    # Objetivo:
    # =====================================
    copro_response_file = os.path.join(base_path, "Copro_Response.json")

    # =====================================
    # 0.3. CONFIGURACIÓN Y LLAMADA A LA API
    # =====================================

    # -------------------------
    # 0.3.1 CONFIGURACIÓN API
    # -------------------------
    AUTH_URL = "https://subsidios.coprocenva.com/api/v1/auth/token"
    CARTERA_URL_BASE = "https://subsidios.coprocenva.com/api/v1/digitalcredit/cartera"

    USER_NAME = "dXNlckFwaVdlYg=="
    PASSWORD = "Q29wcm9jZW52YUFBcGlUZWNuZW9sb2dpYTIwMjVDbGF2ZVN1cGVyU2VjcmV0YQ=="

    def generar_token_copro():
        payload = {
            "userName": USER_NAME,
            "password": PASSWORD
        }
        headers = {"accept": "*/*", "Content-Type": "application/json"}
        response = requests.post(AUTH_URL, json=payload, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Error autenticando: {response.status_code} - {response.text}")

        data = response.json()
        token = (data.get("token") or data.get("access_token") or 
                 data.get("accessToken") or data.get("jwt") or 
                 data.get("bearerToken"))

        if not token:
            raise Exception("No se encontró token en la respuesta")

        return token

    def obtener_cartera_copro(identificacion):
        token = generar_token_copro()
        url = f"{CARTERA_URL_BASE}/{identificacion}"
        headers = {"Authorization": f"Bearer {token}"}

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(
                f"Error consultando cartera ({identificacion}): "
                f"{response.status_code} - {response.text}"
            )
        return response.json()
    
    # -------------------------
    # 0.3.2 FUNCIONES DE NORMALIZACIÓN
    # -------------------------

    def _fecha_aaaammdd_a_iso(valor):
        """Convierte 19850418 -> '1985-04-18'. Si no puede, devuelve ''."""
        if valor in (None, ""):
            return ""
        s = str(valor).strip()
        try:
            dt = datetime.strptime(s, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return ""

    def _fecha_ddmmyyyy_a_iso(valor):
        """Convierte '31/10/2026' -> '2026-10-31'. Si no puede, devuelve ''."""
        if not valor:
            return ""
        s = str(valor).strip()
        try:
            dt = datetime.strptime(s, "%d/%m/%Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return ""

    def normalizar_copro_response(copro):
        """
        Recibe el JSON crudo que devuelve la API de Coprocenva
        y devuelve un diccionario con nombres normalizados para el motor.
        """
        copro = _extraer_payload_copro(copro)
        datos = {}

        # --- Identificación / datos personales ---
        datos["id_asociado"]         = copro.get("id")
        datos["nombre"]              = copro.get("nom")
        datos["apellido"]            = copro.get("apellido")
        datos["nombre_completo"]     = f'{copro.get("nom", "")} {copro.get("apellido", "")}'.strip()
        datos["tipo_identificacion"] = copro.get("tipoIden")

        datos["fecha_nacimiento"]    = _fecha_aaaammdd_a_iso(copro.get("fecNac"))
        datos["fecha_ingreso_coop"]  = _fecha_aaaammdd_a_iso(copro.get("fecIng"))

        # --- Crédito principal ---
        datos["numero_credito"]        = copro.get("nroCredito")
        datos["fecha_vencimiento"]     = _fecha_ddmmyyyy_a_iso(copro.get("fechaVencimiento"))
        datos["plazo_inicial_meses"]   = copro.get("plazoInicialMeses")
        datos["mora_al_corte"]         = copro.get("moraAlCorte")
        datos["cuotas_pagadas"]        = copro.get("cuotasPagadas")
        datos["modalidad_credito"]     = copro.get("modalidad")
        datos["destino_credito"]       = copro.get("destino")
        datos["tasa_efectiva_anual"]   = copro.get("tasaInteresEfectiva")
        datos["valor_prestamo"]        = copro.get("valorPrestamo")
        datos["saldo_capital"]         = copro.get("saldoCapital")

        # --- Garantías / oficina / desembolso ---
        datos["fecha_avaluo"]             = copro.get("fechaAvaluo")
        datos["tipo_garantia"]            = copro.get("tipoGarantia")
        datos["oficina"]                  = copro.get("oficina")
        datos["fecha_desembolso_inicial"] = _fecha_aaaammdd_a_iso(copro.get("fehaDesembolsoInicial"))

        # --- Aportes / ahorros ---
        datos["saldo_aportes"]       = copro.get("saldoAportes")
        datos["ahorro_permanente"]   = copro.get("ahorroPerm")

        # --- Deuda consumo COPRO ---
        datos["deuda_consumo_coop"]  = copro.get("deudaConsumoCoop")
        datos["cuota_consumo_coop"]  = copro.get("cuotaConsumoCoop")

        # --- Rotativos ---
        datos["cupo_rotativos_coop"]   = copro.get("cupoRotativosCoop")
        datos["deuda_rotativos_coop"]  = copro.get("deudaRotativosCoop")
        datos["cuota_rotativos_coop"]  = copro.get("cuotaRotativosCoop")

        # --- Comercial ---
        datos["deuda_comercial_coop"]  = copro.get("deudaComercialCoop")
        datos["cuota_comercial_coop"]  = copro.get("cuotaComercialCoop")

        # --- Microcrédito ---
        datos["deuda_micro_coop"]      = copro.get("deudaMicroCoop")
        datos["cuota_micro_coop"]      = copro.get("cuotaMicroCoop")


        # --- Vivienda (API COPRO) ---
        datos["deuda_vivienda_coop"] = copro.get("deudaViviendaCoop") or 0
        datos["cuota_vivienda_coop"] = copro.get("cuotaViviendaCoop") or 0

        # --- Activos ---
        valor_activos_raw = copro.get("valorActivos")
        try:
            datos["valor_activos"] = float(valor_activos_raw) if valor_activos_raw not in (None, "") else 0.0
        except (TypeError, ValueError):
            datos["valor_activos"] = 0.0

        # --- Moras históricas ---
        datos["max_mora_6m"]     = copro.get("maxMora6Coop")
        datos["max_mora_3m"]     = copro.get("maxMora3Coop")
        datos["max_mora_12m"]    = copro.get("maxMora12Coop")
        datos["max_mora_24m"]    = copro.get("maxMora24Coop")
        datos["max_mora_1m"]     = copro.get("maxMora1Coop")
        datos["max_mora_hist"]   = copro.get("maxMoraCoop")

        # --- Meta / control ---
        datos["fecha_ingreso_bd"] = copro.get("fecingbd")

        return datos


    # -------------------------
    # 0.3.3 LLAMADA O LECTURA LOCAL SEGÚN process_type
    # -------------------------
    identificacion = str(chat_input.get("id", ""))

    # process_type == 1 → SOLO LEE ARCHIVO LOCAL
    # process_type == 2 → CONSULTA API Y GUARDA COPIA
    if process_type == 1:
        print("[INFO] process_type = 1 → Se leerá respuesta local de Coprocenva")

        if os.path.exists(copro_response_file):
            with open(copro_response_file, "r", encoding="utf-8") as f:
                copro_response = json.load(f)
        else:
            print(f"[ERROR] Archivo local no encontrado: {copro_response_file}")
            copro_response = {}

    elif process_type == 2:
     print("[INFO] process_type = 2 → Consultando API de Coprocenva")

    try:
        copro_response = obtener_cartera_copro(identificacion)

        # EN CLOUD: NO guardar copia local (filesystem efímero / ruta no disponible)
        # with open(copro_response_file, "w", encoding="utf-8") as f:
        #     json.dump(copro_response, f, indent=4, ensure_ascii=False)

    except Exception as e:
        # EN CLOUD: APAGADO (sin ruido en logs)
        print(f"[ADVERTENCIA] Error consultando API: {e}")

        # EN CLOUD: sin fallback a archivo local
        copro_response = {}


    # -------------------------
    # 0.3.4 NORMALIZACIÓN DE RESPUESTA API
    # -------------------------
    if copro_response:
        datos_copro = normalizar_copro_response(_extraer_payload_copro(copro_response))
    else:
        datos_copro = {}   

    # =====================================
    # PASO 0.4 – Retorno de insumos base del motor
    # =====================================
    return (
        datos_copro,
        chat_input,
        copro_response
    )

# ============================
# # SECCIÓN AUXILIAR – Archivos adicionales del motor
# ============================

archivos_inputs = {
    "TAYLOR": os.path.join(base_path, "TAYLOR.json"),
    "CAPA_WANT": os.path.join(base_path, "CAPA_WANT.json"),
    "BD_COOP": os.path.join(base_path, "BD_COOP.json") 
}

# ============================
# SECCIÓN AUXILIAR – Función para obtener ingreso total (Experian)
# ============================

def obtener_ingreso_total(response_exp):
    try:
        modelos = response_exp["ReportHDCplus"].get("models", [])
        for modelo in modelos:
            variables = modelo.get("variables", [])
            for var in variables:
                nombre = str(var.get("name", "")).upper()
                if "INGRESO" in nombre or "INCOME" in nombre:
                    valor = float(var.get("value", 0) or 0)
                    if valor > 0:
                        print(f"[DEBUG] Ingreso encontrado: {nombre} = {valor}")
                        return valor
        return 0
    except Exception:
        return 0


# ============================
# Paso 1: Procesar Experian
# ============================

# =====================================
# 1.1 CONFIGURACIÓN EXPERIAN (PRODUCCIÓN)
# =====================================

EXPERIAN_PROD = {
    # URLs PRODUCCIÓN de Experian / Datacrédito (HDCplus)
    "token_url": "https://api.datacredito.com.co/spla/oauth2/v1/token",
    "service_url": "https://api.datacredito.com.co/cs/credit-history/v1/hdcplus",

    # Credenciales OAuth (Generar_TOKEN) — ver colección POSTMAN "COPRO EXP REST PROD"
    "client_id": "0oau9hgibplxxidI81t7",
    "client_secret": "w2JY9ClUzDcMphJkBZvC0BRCuj0Ks1LcBYQ4E00xDoOJjqmbxEatnCZdZyW_q55C",
    "username": "2-891900492.4@datacredito.com.co",   
    "password": "Want202511#",   

    # Credenciales de suscriptor (Servicio HDCplus) — ver body del request "Servicio"
    "user_suscriptor": "891900492",       
    "password_suscriptor": "62HFF",   

    # Headers de servicio (si  contrato lo requiere)
    # En PROD, Experian suele validar la IP de salida. Aquí va la IP fija de Azure cuando se tenga.
    "server_ip": "167.99.125.157",  # ej: 200.118.16.152

    "product_id": "64",
    "info_account_type": "1",
    "codigos": "TOM-001",
}

# Alias para no tocar el resto del código:
# Alias de compatibilidad: el motor histórico esperaba un alias legado; se reemplaza por una configuración PROD.
EXPERIAN_HDCPLUS_CFG = EXPERIAN_PROD


# ============================
# 1.2 TOKEN HDCplus (PRODUCCIÓN)
# ============================

def generar_token_experian_demo() -> str:
    """
    Llama al endpoint de PRODUCCIÓN de Experian y retorna el access_token.
    Usa la configuración definida en EXPERIAN_HDCPLUS_CFG.
    """
    cfg = EXPERIAN_HDCPLUS_CFG

    url = cfg["token_url"]

    headers = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "Content-Type": "application/json",
    }

    payload = {
        "username": cfg["username"],
        "password": cfg["password"],
    }

    # resp = requests.post(url, headers=headers, json=payload)
    print(f"[INFO] PAYLOAD token Experian... ")
    print(f"[INFO] PAYLOAD token Experian url : {url}")
    print(f"[INFO] PAYLOAD token Experian headers : {headers}")
    print(f"[INFO] PAYLOAD token Experian payload : {payload}")
    print(f"[EXPERIAN TOKEN] Llamando URL: {url}")
    print(f"[EXPERIAN TOKEN] Headers enviados: {headers}")
    resp = proxy_request("POST", url, headers=headers, json_body=payload, timeout=30, retries=2, backoff_factor=1)
    print(f"[EXPERIAN TOKEN] Status code: {resp.status_code}")
    print(f"[EXPERIAN TOKEN] Respuesta cruda: {resp.text[:500]}")
    resp.raise_for_status()
    data = resp.json()

    token = (
        data.get("access_token")
        or data.get("token")
        or data.get("id_token")
    )

    if not token:
        raise RuntimeError(f"No se encontró token en respuesta de token: {data}")

    return token


# ============================
# 1.3 SERVICIO HDCplus (PRODUCCIÓN)
# ============================

def obtener_experian_demo(chat_input: dict) -> dict:
    """
    Llama únicamente al servicio de PRODUCCIÓN de Experian HDCplus.
    """
    cfg = EXPERIAN_HDCPLUS_CFG

    token = generar_token_experian_demo()

    url = cfg["service_url"]

    headers = {
        "Content-Type": "application/json",
        "serverIpAddress": cfg["server_ip"],
        "ProductId": cfg["product_id"],
        "InfoAccountType": cfg["info_account_type"],
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "Authorization": f"Bearer {token}",
    }

    # Datos del suscriptor (los mismos que en la request HDCplus (PROD) de Postman)
    user_suscriptor = cfg["user_suscriptor"]
    password_suscriptor = cfg["password_suscriptor"]

    # Datos del cliente desde chat_input
    person_id_number = str(chat_input.get("id", ""))
    person_id_type = chat_input.get("id_type", 1)
    person_last_name = chat_input.get("last_name", "")

    # Identificación de la transacción
    request_uuid = str(uuid.uuid4())
    # Zona horaria Colombia (UTC-5)
    now_col = datetime.now(timezone(timedelta(hours=-5)))
    date_time_iso = now_col.isoformat(timespec="seconds")

    body = {
        "user": user_suscriptor,
        "password": password_suscriptor,
        "identifyingTrx": {
            "requestUUID": request_uuid,
            "dateTime": date_time_iso,
            "originatorChannelName": "CONEXRED-01",
            "originatorChannelType": "42",
        },
        "identifyingUser": {
            "person": {
                "personId": {
                    "personIdNumber": person_id_number,
                    "personIdType": person_id_type,
                },
                "personLastName": person_last_name,
            }
        },
        "parameters": [
            {
                "type": "0",
                "nameParameter": "codigos",
                "valueParameter": cfg["codigos"],
            }
        ],
    }

    print(f"[EXPERIAN HDC] Llamando URL: {url}")
    print(f"[EXPERIAN HDC] Headers enviados: {headers}")
    print(f"[EXPERIAN HDC] Body enviado: {json.dumps(body)[:500]}")
    resp = proxy_request("POST", url, headers=headers, json_body=body, timeout=30, retries=2, backoff_factor=1)
    print(f"[EXPERIAN HDC] Status code: {resp.status_code}")
    print(f"[EXPERIAN HDC] Respuesta cruda: {resp.text[:1000]}")
    resp.raise_for_status()
    return resp.json()

# ==================================
# 1.4 CAPA CONTROLADORA (archivo / API)
# ==================================

def obtener_response_experian(chat_input: dict) -> dict:
    """
    Usa ambiente PRODUCCIÓN (según configuración).

    - process_type_exp = 1 -> Lee el JSON local (EXP_Response.json)
    - process_type_exp = 2 -> Llama la API PROD HDCplus y guarda el JSON en ese archivo

    """
    

    process_type_exp = int(chat_input.get("process_type_exp", 1))

    # --------- MODO 1: ARCHIVO LOCAL ----------
    if process_type_exp == 1:
        ubication = r"C:/Want/Motores/Coprocenva/s1"
        response_file = os.path.join(ubication, "EXP_Response.json")
        with open(response_file, "r", encoding="utf-8") as f:
            return json.load(f)

    # --------- MODO 2: API PROD EXPERIAN ----------
    elif process_type_exp == 2:
        try:
          response_exp = obtener_experian_demo(chat_input)
          print(f"[INFO] Respuesta Experian HDCplus obtenida correctamente.")

        # EN CLOUD: NO guardar en archivo (filesystem efímero / ruta no disponible)
        # os.makedirs(ubication, exist_ok=True)
        # with open(response_file, "w", encoding="utf-8") as f:
        #     json.dump(response_exp, f, indent=4, ensure_ascii=False)

          return response_exp

        except Exception as e:
            print(f"[ADVERTENCIA] Error llamando API PROD Experian HDCplus: {e}")
            return {}
        # EN CLOUD: APAGADO (sin ruido en logs)
        # EN CLOUD: sin fallback a archivo local
         

    else:
      raise ValueError(f"process_type_exp inválido: {process_type_exp}")

    
# ============================
# 1.5 PROCESAMIENTO RESPUESTA EXPERIAN
# ============================

def procesar_response(response, tablas):
    """Procesa la respuesta Experian (HDCplus).
       Usa todos los créditos para moras y solo los vigentes para totales globales."""
    jerarquia = ['C', 'D', '6', '5', '4', '3', '2', '1', 'N', '-', ' ']
    NIT_EXCLUIR_COPRO = "891900492"  # NIT Coprocenva sin dígito

    def calcular_mora(vector):
        vector = list(vector.strip())
        vector_filtrado = [str(c) for c in vector if str(c) in jerarquia]
        return {
            "Delinquency_0": vector_filtrado[0] if len(vector_filtrado) >= 1 else '',
            "Delinquency_3M": min(vector_filtrado[:3], key=lambda x: jerarquia.index(x)) if len(vector_filtrado) >= 3 else '',
            "Delinquency_6M": min(vector_filtrado[:6], key=lambda x: jerarquia.index(x)) if len(vector_filtrado) >= 6 else '',
            "Delinquency_12M": min(vector_filtrado[:12], key=lambda x: jerarquia.index(x)) if len(vector_filtrado) >= 12 else ''
        }

    # Créditos para moras (todos)
    liabilities_todas = []
    for key in ["liabilities", "creditCard", "closedLiabilities", "cancelledAccounts", "otherLoans"]:
        bloque = response["ReportHDCplus"].get(key, [])
        if isinstance(bloque, dict):
            bloque = [bloque]
        liabilities_todas.extend(bloque)

    # Créditos para totales (solo vigentes)
    liabilities_vigentes = []
    for key in ["liabilities", "creditCard"]:
        bloque = response["ReportHDCplus"].get(key, [])
        if isinstance(bloque, dict):
            bloque = [bloque]
        liabilities_vigentes.extend(bloque)

    acumuladores = defaultdict(lambda: defaultdict(float))
    delinquency_por_entidad = defaultdict(list)

    def evaluar_y_sumar(entidad_id, acum_nombre, condicion, valor):
        if condicion:
            acumuladores[entidad_id][acum_nombre] += valor

    # Moras: todas las obligaciones
    for item in liabilities_todas:
        liability = item.get("liabilitiesAccount", {}) or item.get("creditCardAccount", {})
        vector = liability.get("businessBehaviourVectorProduct", "") or "N"
        mora = calcular_mora(vector)
        cuenta = item.get("account", {})
        person_id_number = str(cuenta.get("personId", {}).get("personIdNumber", "")).strip()
        normalized_id = person_id_number.lstrip("0")
        if normalized_id == NIT_EXCLUIR_COPRO:
            continue
        delinquency_por_entidad[normalized_id].append(mora)
    # Totales: solo créditos vigentes (estilo Fesicol)
    liabilities = response["ReportHDCplus"].get("liabilities", [])
    credit_cards = response["ReportHDCplus"].get("creditCard", [])

    for fuente, items in [("Liability", liabilities), ("CreditCard", credit_cards)]:
        for item in items:
            cuenta = item.get("account", {})
            liability = item.get("liabilitiesAccount" if fuente == "Liability" else "creditCardAccount", {}) or {}
            valores = item.get("values", [{}])[0]

            payment_type = str(liability.get("paymentType", ""))

            accountTypeDesc = str(cuenta.get("accountTypeDesc", "")).upper()

            person_id_number = str(cuenta.get("personId", {}).get("personIdNumber", "")).strip()
            normalized_id = person_id_number.lstrip("0")
            es_copro = (normalized_id == NIT_EXCLUIR_COPRO)

            if es_copro:
                print("[DEBUG] COPROCENVA incluida en CUOTAS pero excluida en DEUDA Experian:",
                    cuenta.get("businesslinename") or cuenta.get("businessLineName"))

            debt = 0 if es_copro else valores.get("debtBalance", 0)

            saldo = valores.get("debtBalance", 0)
            cuota_reportada = valores.get("valueMonthlyPayment", 0)

            if fuente == "CreditCard":
                cuota = saldo / 36
                tipo_credito_codigo = "2"   # consumo por defecto para tarjetas
            else:
                cuota = (saldo / 36) if (cuota_reportada == 0 and saldo != 0) else cuota_reportada
                tipo_credito_codigo = str(item.get("featuresLiabilities", {}).get("typeOfCredit", ""))

            monto_inicial = valores.get("initialValue", 0)

            # FIX 1: nunca negativos
            if debt < 0:
                debt = 0
            if cuota < 0:
                cuota = 0

            # FIX 2: condición de vigencia
            #es_vigente = (payment_type == "0")

            if tipo_credito_codigo == "3":
                evaluar_y_sumar(normalized_id, "bal_hous_ext", payment_type == "0", debt)
                evaluar_y_sumar(normalized_id, "ext_installment_hous", payment_type == "0", cuota)
                evaluar_y_sumar(normalized_id, "init_value_hous", True, monto_inicial)
            elif accountTypeDesc in {"LVE", "CVH", "CVD"}:
                evaluar_y_sumar(normalized_id, "bal_veh_ext", payment_type == "0", debt)
                evaluar_y_sumar(normalized_id, "ext_installment_veh", payment_type == "0", cuota)
                evaluar_y_sumar(normalized_id, "init_value_veh", True, monto_inicial)
            elif tipo_credito_codigo in {"0", "1", "2", "4", "5", "6"}:
                evaluar_y_sumar(normalized_id, "bal_cons_ext", payment_type == "0", debt)
                evaluar_y_sumar(normalized_id, "ext_installment_cons", payment_type == "0", cuota)
                evaluar_y_sumar(normalized_id, "init_value_cons", True, monto_inicial)
            else:
                evaluar_y_sumar(normalized_id, "bal_other_ext", payment_type == "0", debt)
                evaluar_y_sumar(normalized_id, "ext_installment_other", payment_type == "0", cuota)
                evaluar_y_sumar(normalized_id, "init_value_other", True, monto_inicial)

    try:
        credit_score = response["ReportHDCplus"]["models"][0]["scoreValue"]
    except Exception:
        credit_score = "N/A"

    return acumuladores, credit_score, delinquency_por_entidad


# ============================
# Paso 2: TransUnion
# ============================

# -----------------------------------------
# 2.1 – Consulta directa a la API de TU Combo
# -----------------------------------------

def obtener_transunion_desde_api(chat_input: dict):
    url = "https://tucoapplicationserviceuat.transunion.co/ws/v1/rest/consultarCombo"
    auth_user = "<TU_API_USER>"
    auth_pass = "<TU_API_PASS>"
    headers = {"Content-Type": "application/json"}

    payload = {
        "codigoInformacion": "1901",
        "tipoIdentificacion": str(chat_input.get("id_type", 1)),
        "numeroIdentificacion": str(chat_input.get("id", "")),
        "motivoConsulta": "24",
        "idPolitica": "6356",
        "numeroCuenta": "",
        "tipoEntidad": "",
        "tipoCuenta": "",
        "codigoEntidad": ""
    }

    resp = requests.post(url, auth=(auth_user, auth_pass), headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()

# -----------------------------------------
# 2.2 – Origen de datos TU: API vs archivo local
# -----------------------------------------

def obtener_response_transunion(chat_input: dict):
    ubication = r"C:/Want/Motores/Coprocenva/s1"
    tu_file = os.path.join(ubication, "TU_Response.json")

    process_type_tu = int(chat_input.get("process_type", 1))

    # 2.2.1 – Modo archivo local

    if process_type_tu == 1:
        print("[INFO] TU: process_type = 1 → Leer archivo local")
        if os.path.exists(tu_file):
            with open(tu_file, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            print(f"[ERROR] Archivo local TU no encontrado: {tu_file}")
            return {}
        
    # 2.2.2 – Modo API (cloud: sin copia local)

    elif process_type_tu == 2:
        print("[INFO] TU: process_type = 2 → Llamar API TU")
        try:
           response_tu = obtener_transunion_desde_api(chat_input)

        # EN CLOUD: NO guardar copia local
        # with open(tu_file, "w", encoding="utf-8") as f:
        #     json.dump(response_tu, f, indent=4, ensure_ascii=False)

           return response_tu

        except Exception as e:
        # EN CLOUD: APAGADO (sin ruido)
        # print(f"[ADVERTENCIA] Error API TU: {e}")

        # EN CLOUD: sin fallback a archivo local
          return {}

    else:
        raise ValueError(f"process_type inválido: {process_type_tu}")


# -----------------------------------------
# 2.3 – Procesamiento de la respuesta TU
# -----------------------------------------

def procesar_response_transunion(response_tu):
    """Usa todas las obligaciones para moras, pero solo vigentes para totales."""
    jerarquia = ['C','D','6','5','4','3','2','1','N','-',' ']

    def calcular_mora(vector):
        vector = vector.replace(" ", "").replace("|", "")
        vector_filtrado = [c for c in vector if c in jerarquia]
        return {
            "Delinquency_0": vector_filtrado[0] if len(vector_filtrado)>=1 else '',
            "Delinquency_3M": min(vector_filtrado[:3], key=lambda x: jerarquia.index(x)) if len(vector_filtrado)>=3 else '',
            "Delinquency_6M": min(vector_filtrado[:6], key=lambda x: jerarquia.index(x)) if len(vector_filtrado)>=6 else '',
            "Delinquency_12M": min(vector_filtrado[:12], key=lambda x: jerarquia.index(x)) if len(vector_filtrado)>=12 else ''
        }

    acumuladores = defaultdict(lambda: defaultdict(float))
    delinquency_por_entidad = defaultdict(list)
    info_comercial = response_tu.get("Informacion_Comercial_154", {})

    # Moras: todas las obligaciones
    obligaciones_todas = []
    for tipo in ["SectorFinancieroAlDia", "SectorFinancieroMora", "SectorFinancieroExtinguidas"]:
        bloque = info_comercial.get(tipo, {}).get("Obligacion", [])
        if isinstance(bloque, dict):
            bloque = [bloque]
        obligaciones_todas.extend(bloque)

    # Totales: solo vigentes
    obligaciones_vigentes = []
    for tipo in ["SectorFinancieroAlDia", "SectorFinancieroMora"]:
        bloque = info_comercial.get(tipo, {}).get("Obligacion", [])
        if isinstance(bloque, dict):
            bloque = [bloque]
        obligaciones_vigentes.extend(bloque)
    # Cuotas: SOLO obligaciones al día (ignora mora y extinguidas)
    obligaciones_al_dia = []
    bloque = info_comercial.get("SectorFinancieroAlDia", {}).get("Obligacion", [])
    if isinstance(bloque, dict):
        bloque = [bloque]
    obligaciones_al_dia.extend(bloque)
    FACTOR_CONVERSION = 1000
    print("[INFO] Se aplica conversión fija de TransUnion: todos los valores multiplicados x1000.")

    # Moras
    for obl in obligaciones_todas:
        entidad = obl.get("NombreEntidad", "DESCONOCIDA")
        comportamientos = obl.get("Comportamientos", "")
        mora = calcular_mora(comportamientos)
        delinquency_por_entidad[entidad].append(mora)

    # Totales (solo vigentes)
    def to_float_tu(x):
      """Convierte strings TU a float. Si viene vacío/None/no numérico, retorna 0."""
      try:
        s = str(x).strip()
        return float(s) if s not in ("", "None", "null") else 0.0
      except Exception:
        return 0.0

    for obl in obligaciones_vigentes:
        entidad = obl.get("NombreEntidad", "DESCONOCIDA")
        modalidad = obl.get("ModalidadCredito", "")

        # Conversión a pesos (TU viene en miles)
        saldo = to_float_tu(obl.get("SaldoObligacion", 0)) * FACTOR_CONVERSION
        cuota = to_float_tu(obl.get("ValorCuota", 0)) * FACTOR_CONVERSION
        monto_inicial = to_float_tu(obl.get("ValorInicial", 0)) * FACTOR_CONVERSION

        # FIX anti-riesgo: no permitir negativos
        if saldo < 0:
           saldo = 0
        if cuota < 0:
           cuota = 0
        if monto_inicial < 0:
           monto_inicial = 0

        if modalidad == "CONS":
         acumuladores[entidad]["bal_cons_ext"] += saldo
         acumuladores[entidad]["ext_installment_cons"] += cuota
         acumuladores[entidad]["init_value_cons"] += monto_inicial
        elif modalidad == "VIVI":
         acumuladores[entidad]["bal_hous_ext"] += saldo
         acumuladores[entidad]["ext_installment_hous"] += cuota
         acumuladores[entidad]["init_value_hous"] += monto_inicial
        elif modalidad in {"VEHI", "AUTO"}:
         acumuladores[entidad]["bal_veh_ext"] += saldo
         acumuladores[entidad]["ext_installment_veh"] += cuota
         acumuladores[entidad]["init_value_veh"] += monto_inicial
        else:
         acumuladores[entidad]["bal_other_ext"] += saldo
         acumuladores[entidad]["ext_installment_other"] += cuota
         acumuladores[entidad]["init_value_other"] += monto_inicial

    # Cuotas (SOLO al día)
    for obl in obligaciones_al_dia:
        entidad = obl.get("NombreEntidad", "DESCONOCIDA")
        modalidad = (obl.get("ModalidadCredito") or "").strip().upper()

        cuota = to_float_tu(obl.get("ValorCuota", 0)) * FACTOR_CONVERSION

        if cuota < 0:
           cuota = 0

        if modalidad == "CONS":
         acumuladores[entidad]["ext_installment_cons"] += cuota
        elif modalidad == "VIVI":
         acumuladores[entidad]["ext_installment_hous"] += cuota
        elif modalidad in {"VEHI", "AUTO"}:
         acumuladores[entidad]["ext_installment_veh"] += cuota
        else:
         acumuladores[entidad]["ext_installment_other"] += cuota


    try:
        credit_score_transunion = response_tu["CreditVision_5694"]["fechaCorte"][0]["variables"][0]["valor"]
    except Exception:
        credit_score_transunion = "N/A"

    return acumuladores, credit_score_transunion, delinquency_por_entidad


# ============================
# CONFIGURACIÓN EXPERIAN INGRESOS (PRODUCCIÓN - QUEMADA EN CÓDIGO)
# ============================


OKTA_INCOMES_TOKEN_URL = "https://experian-latamb.okta.com/oauth2/aus8jhfmnuDjZO8Q11t7/v1/token"
OKTA_INCOMES_BASIC_B64 = "Basic MG9hMThiYWc4eHhtOVdtbzgxdDg6cWt6UUJ5dUdPZ3dRbldlOW1TU3pObFpOTDdFNGlfLUw5czJOYjlURjVUbnRPVl9wS1g0NnB3RjlUTmxaNzM5TQ=="
OKTA_INCOMES_USERNAME  = "2-891900492.3@datacredito.com.co"
OKTA_INCOMES_PASSWORD  = "Want202511#"  
OKTA_INCOMES_SCOPE     = "expco_incomes"

INCOME_INDICATOR_URL   = "https://servicesesb.datacredito.com.co:444/cs/incomes/v1/income/indicator"
INCOME_CLIENT_ID       = "<INCOME_CLIENT_ID>"
INCOME_CLIENT_SECRET   = "<INCOME_CLIENT_SECRET>"

# Datos del suscriptor (query params del servicio incomes)
INCOME_TIPO_ID_USUARIO         = "2"
INCOME_IDENTIFICACION_USUARIO  = "891900492"   
INCOME_TIPO_ID_SUSCRIPTOR      = "2"
INCOME_NIT_SUSCRIPTOR          = "891900492"           
INCOME_NOMBRE_SUSCRIPTOR       = "COOPERATIVA DE AHORRO Y CREDITO CO PROCENVA"

# Parametría del servicio
INCOME_PRODUCTO_ID        = "12"
INCOME_CANAL_CONSULTA     = "2"
INCOME_PRODUCTO_CONSULTA  = "1"


# ============================
# Paso 3: Ingreso Experian (Datacrédito Incomes)
# ============================

# --- 3.1: Obtener token en OKTA ---

def obtener_token_okta_ingresos():
    """
    Obtiene el access_token desde OKTA para consumir el servicio
    de ingresos (Datacrédito / Experian).
    """
    url = OKTA_INCOMES_TOKEN_URL

    headers = {
        "Authorization": OKTA_INCOMES_BASIC_B64,
        "content-type": "application/x-www-form-urlencoded",
        "accept": "application/json",
    }

    # En la colección de Postman, estos valores van como query params.
    # requests los puede enviar como form-urlencoded sin problema.
    data = {
        "grant_type": "password",
        "username": OKTA_INCOMES_USERNAME,
        "password": OKTA_INCOMES_PASSWORD,
        "scope": OKTA_INCOMES_SCOPE,
    }

    resp = requests.post(url, headers=headers, data=data)
    resp.raise_for_status()

    token = resp.json().get("access_token")
    if not token:
        raise Exception("No se obtuvo access_token del servicio de OKTA (ingresos).")

    return token


# --- 3.2: Llamar servicio de ingresos Datacrédito ---

def consultar_ingresos_datacredito(identificacion_buscar, ingreso_validar, token):
    """
    Consulta el servicio de ingresos de Datacrédito para una identificación
    y un ingreso declarado (IngresoValidar).
    """
    url = INCOME_INDICATOR_URL

    headers = {
        "access_token": token,
        "client_id": INCOME_CLIENT_ID,
        "client_secret": INCOME_CLIENT_SECRET,
        "accept": "application/json",
    }

    params = {
        "TipoIdentificacionUsuario": INCOME_TIPO_ID_USUARIO,
        "IdentificacionUsuario": INCOME_IDENTIFICACION_USUARIO,
        "TipoIDSuscriptor": INCOME_TIPO_ID_SUSCRIPTOR,
        "NitSuscriptor": INCOME_NIT_SUSCRIPTOR,
        "NombreSuscriptor": INCOME_NOMBRE_SUSCRIPTOR,
        "TipoIdBuscar": "1",  # CC (mantengo igual a tu versión actual)
        "IdentificacionBuscar": identificacion_buscar,
        "IngresoValidar": ingreso_validar,
        "ProductoId": INCOME_PRODUCTO_ID,
        "CanalConsulta": INCOME_CANAL_CONSULTA,
        "ProductoConsulta": INCOME_PRODUCTO_CONSULTA,
        "HTTP": "1.1",
        "Accept-Encoding": "gzip,deflate",
    }

    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


# --- 3.3: Obtener respuesta de ingreso según process_type_ingreso ---

def obtener_response_ingreso_experian(chat_input: dict) -> dict:
    """
    process_type_ingreso = 1 -> lee EXP_VrIngreso.json (local)
    process_type_ingreso = 2 -> consulta la API de ingresos y guarda EXP_VrIngreso.json
    """
    

    process_type_ingreso = int(chat_input.get("process_type_ingreso", 1))

    if process_type_ingreso == 1:
        ubication = r"C:/Want/Motores/Coprocenva/s1"
        ingreso_file = os.path.join(ubication, "EXP_VrIngreso.json")
        # MODO LOCAL
        with open(ingreso_file, "r", encoding="utf-8") as f:
            return json.load(f)

    elif process_type_ingreso == 2:
       # MODO API (cloud: sin copia local)
       try:
           identificacion = str(chat_input.get("id", ""))
           ingreso_validar = chat_input.get("ingreso_asociado")
           token = obtener_token_okta_ingresos()
           respuesta = consultar_ingresos_datacredito(
            identificacion_buscar=identificacion,
            ingreso_validar=ingreso_validar,    
            token=token)
           save_json_blob_by_id(chat_input.get("id"), "EXP_VrIngreso.json", respuesta)
           return respuesta

        # EN CLOUD: NO guardar archivo local
        # with open(ingreso_file, "w", encoding="utf-8") as f:
        #     json.dump(respuesta, f, indent=4, ensure_ascii=False)

            

       except Exception as e:
            # EN CLOUD: APAGADO (sin ruido)
            # print(f"[ADVERTENCIA] Error llamando API de ingresos Datacrédito: {e}")

            # EN CLOUD: sin fallback a archivo local
            return {}

    else:
      raise ValueError(f"process_type_ingreso inválido: {process_type_ingreso}")


# --- 3.4: Parseo de la respuesta -> ingreso promedio Y meses de continuidad ---

def procesar_response_ingreso_experian(response_ingreso: dict) -> dict:
    """
    Procesa la respuesta de la API de ingresos de Datacrédito/Experian
    y devuelve un diccionario con:
      - ingreso_promedio: float (el que usará el motor)
      - meses_continuidad: int o None

    Estructura esperada (como EXP_VrIngreso.json):
      response_ingreso["indicadores"]["..."]
      response_ingreso["resumen_general_ingresos"]["meses_continuidad"]
    """

    indicadores = response_ingreso.get("indicadores", {}) or {}
    resumen = response_ingreso.get("resumen_general_ingresos", {}) or {}

    # Lógica original para ingreso_promedio:
    # 1) promedio_ingresos_cotizante
    # 2) promedio_ult_doce_meses
    ingreso_promedio = (
        resumen.get("promedio_ingresos_cotizante")
        or indicadores.get("promedio_ult_doce_meses")
        or 0
    )

    # Cast ingreso_promedio a float
    try:
        ingreso_promedio = float(ingreso_promedio)
    except (TypeError, ValueError):
        ingreso_promedio = 0.0

    # EXTRA: meses de continuidad desde resumen_general_ingresos
    meses_continuidad = resumen.get("meses_continuidad")

    # Cast meses_continuidad a int (si aplica)
    try:
        meses_continuidad = int(meses_continuidad) if meses_continuidad not in (None, "", 0) else None
    except (TypeError, ValueError):
        meses_continuidad = None

    print(
        "[DEBUG procesar_response_ingreso_experian] "
        f"ingreso_promedio={ingreso_promedio} | meses_continuidad={meses_continuidad}"
    )

    return {
        "ingreso_promedio": ingreso_promedio,
        "meses_continuidad": meses_continuidad,
    }


# --- 3.5: Paso de ingreso completo para usar en el flujo del motor ---

def paso_ingreso_experian(chat_input: dict) -> dict:
    """
    Paso completo:
      1. Obtiene la respuesta de ingreso (local o API según process_type_ingreso).
      2. Procesa esa respuesta para obtener:
           - ingreso_promedio (float)
           - meses_continuidad (int o None)
      3. Devuelve un dict con ambas variables.

    Retorna:
      {
         "ingreso_promedio": <float>,
         "meses_continuidad": <int | None>
      }
    """
    response_ingreso = obtener_response_ingreso_experian(chat_input)
    info_ingreso = procesar_response_ingreso_experian(response_ingreso)
    return info_ingreso

# --- 3.6: Paso de definición politica de continuidad

# Política de meses mínimos de continuidad por ocupación (decide apartir de la variable continuidad del archivo local o de la API)
MIN_MESES_CONTINUIDAD_POR_OCUPACION = {
    2: 6,
    3: 6,
    4: 12,
    8: 12,
}

# ============================
# Paso 4: Calcular ingreso total y continuidad laboral
# ============================

def calcular_ingreso_total(diccionario_maestro: dict, info_ingreso: dict = None) -> dict:
    """
    Calcula el ingreso total a usar en el motor como el MÍNIMO entre:
      - ingreso_asociado (declarado por el cliente)
      - ingreso promedio validado por Experian (ingreso_promedio de paso_ingreso_experian)

    Además:
      - Guarda Ingreso_Total y Meses_continuidad en resumen_final
      - Guarda Ingreso_total, Meses_continuidad y Cumple_ingreso_total en Motor want
      - Agrega Cumple_continuidad_laboral según ocupación y meses_continuidad

      Política ingreso:
        - Ingreso_total debe ser >= 1,423,500
          * Cumple_ingreso_total = 1 si cumple
          * Cumple_ingreso_total = 2 si incumple

      Política continuidad laboral:
        - Según ocupación (chat_input["ocupacion"]), meses_continuidad debe
          ser >= mínimo definido en MIN_MESES_CONTINUIDAD_POR_OCUPACION
          * Cumple_continuidad_laboral = 1 si cumple
          * Cumple_continuidad_laboral = 2 si incumple o no se puede validar
    """

    # 4.1 Estructuras base
    chat_input = diccionario_maestro.get("chat_input", {}) or {}
    motor = diccionario_maestro.setdefault("Motor want", {})
    resumen = diccionario_maestro.setdefault("resumen_final", {})

    # 4.2 ocupación del cliente
    ocupacion = chat_input.get("ocupacion")
    try:
        ocupacion = int(ocupacion) if ocupacion not in (None, "", 0) else None
    except (TypeError, ValueError):
        ocupacion = None

    # 4.3 Ingreso declarado por el cliente
    ingreso_cliente = chat_input.get("ingreso_asociado")
    try:
        ingreso_cliente = float(ingreso_cliente) if ingreso_cliente not in (None, "", 0) else None
    except (TypeError, ValueError):
        ingreso_cliente = None

    # 4.4 Información de Experian: ingreso + meses
    # Si viene info_ingreso desde afuera, lo usamos.
    # Si no viene, hacemos fallback al comportamiento anterior.
    if info_ingreso is None:
        info_ingreso = paso_ingreso_experian(chat_input)

    ingreso_buro = info_ingreso.get("ingreso_promedio")
    meses_continuidad = info_ingreso.get("meses_continuidad")


    # Cast ingreso Experian
    try:
        ingreso_buro = float(ingreso_buro) if ingreso_buro not in (None, "", 0) else None
    except (TypeError, ValueError):
        ingreso_buro = None

    # Cast meses_continuidad a int 
    try:
        meses_continuidad = int(meses_continuidad) if meses_continuidad not in (None, "", 0) else None
    except (TypeError, ValueError):
        meses_continuidad = None

    # 4.5 Ingreso total = mínimo entre los ingresos válidos
    candidatos = [v for v in (ingreso_cliente, ingreso_buro) if v is not None]
    ingreso_total = min(candidatos) if candidatos else 0.0

    print(
        f"[DEBUG Paso7] ingreso_cliente={ingreso_cliente} | "
        f"ingreso_buro={ingreso_buro} | ingreso_total={ingreso_total} | "
        f"meses_continuidad={meses_continuidad} | ocupacion={ocupacion}"
    )

    # 4.6 Guardar en resumen_final
    resumen["Ingreso_declarado_asociado"] = ingreso_cliente
    resumen["Ingreso_experian_promedio"] = ingreso_buro
    resumen["Ingreso_Total"] = ingreso_total
    resumen["Meses_continuidad"] = meses_continuidad
    diccionario_maestro["resumen_final"] = resumen

    # 4.7 Guardar en Motor want
    motor["Ingreso_total"] = ingreso_total
    motor["Meses_continuidad"] = meses_continuidad

    # 4.8 Política de ingreso
    minimo_ingreso = 1_750_905
    motor["Cumple_ingreso_total"] = 1 if ingreso_total >= minimo_ingreso else 2

    # 4.9 Política de continuidad laboral según ocupación
    min_meses_continuidad = MIN_MESES_CONTINUIDAD_POR_OCUPACION.get(ocupacion)

    if min_meses_continuidad is not None and meses_continuidad is not None:
        motor["Cumple_continuidad_laboral"] = (
            1 if meses_continuidad >= min_meses_continuidad else 2
        )
    else:
        # Decisión: si no hay meses_continuidad o ocupación no está en la tabla,
        # lo marcamos como NO CUMPLE (2). Cámbialo si tu política es distinta.
        motor["Cumple_continuidad_laboral"] = 2

    diccionario_maestro["Motor want"] = motor

    return diccionario_maestro


# ============================
# Paso 5: Moras globales y políticas de riesgo
# ============================

# ------------------------------------------------------------
# 5.1 – Cálculo del vector de moras máximas global
# -----------------------------------------------------------

def calcular_vector_moras_maximas(delinquency_dicts):
    jerarquia = ['C','D','6','5','4','3','2','1','N','-',' ']
    campos = ["Delinquency_0","Delinquency_3M","Delinquency_6M","Delinquency_12M"]
    moras_max = {campo: ' ' for campo in campos}

    for mora_dict in delinquency_dicts:
        for campo in campos:
            actual = mora_dict.get(campo, ' ')
            peor = moras_max.get(campo, ' ')
            if actual not in jerarquia:
                continue
            if peor not in jerarquia:
                peor = ' '
            if jerarquia.index(actual) < jerarquia.index(peor):
                moras_max[campo] = actual
    return moras_max

# ============================
# 5.2 – Política de mora externa 12 meses
# ============================

def evaluar_politica_mora_externa_12m(moras_maximas):
    """
    Política: Mora externa en los últimos 12 Meses < 31 días

    Usamos el campo moras_maximas["Delinquency_12M"], que ya es
    el peor estado de mora de los últimos 12 meses combinando
    Experian + TransUnion.

    Regla:
      - Se considera CUMPLE (1) si la peor mora es:
          '1', 'N', '-' o ' '  (<= 30 días o sin mora / sin dato)
      - Se considera NO CUMPLE (2) si la peor mora es
        peor que '1' (es decir: '2','3','4','5','6','C','D')
    """
    jerarquia = ['C','D','6','5','4','3','2','1','N','-',' ']

    peor_12m = moras_maximas.get("Delinquency_12M", ' ')

    if peor_12m in jerarquia:
        idx_peor = jerarquia.index(peor_12m)
        idx_umbral = jerarquia.index('1')  # 1 = hasta 30 días
        # Si la posición es >= '1' => cumple (máx 30 días o mejor)
        cumple = 1 if idx_peor >= idx_umbral else 2
    else:
        # Si viene algo raro/no reconocido, lo marcamos como NO CUMPLE
        cumple = 2

    return peor_12m, cumple


# ============================
# 5.3 – Política de score mínimo (Experian vs TransUnion)
# ============================

def evaluar_politica_score_minimo(diccionario_maestro, score_exp, score_tu, minimo=700):

    motor = diccionario_maestro.setdefault("Motor want", {})

    # Asegurar que minimo sea numérico
    try:
        minimo = float(minimo)
    except:
        minimo = 700

    def to_float(x):
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)

        try:
            return float(str(x).replace(",", "").strip())
        except:
            return None

    s_exp = to_float(score_exp)
    s_tu  = to_float(score_tu)

    candidatos = [s for s in (s_exp, s_tu) if s is not None]

    if not candidatos:
        score_minimo = None
        cumple = 2  # no cumple
    else:
        score_minimo = min(candidatos)
        cumple = 1 if score_minimo >= minimo else 2

    motor["Score_minimo_buro"] = score_minimo
    motor["Cumple_score_minimo"] = cumple

    return diccionario_maestro



# ============================
# Paso 6: Agregar totales globales por tipo de crédito
# ============================

def agregar_por_tipo_credito_global_desde_filtrado(filtrado):
    resultado = defaultdict(lambda: defaultdict(float))
    for entidad, valores in filtrado.items():
        for k, v in valores.items():
            if "_cons" in k: tipo = "cons"
            elif "_hous" in k: tipo = "hous"
            elif "_veh" in k: tipo = "veh"
            elif "_other" in k: tipo = "other"
            else: continue
            if "bal_" in k:
                resultado[tipo][f"bal_{tipo}_ext"] += v
            elif "ext_installment" in k:
                resultado[tipo][f"ext_installment_{tipo}"] += v
            elif "init_value" in k:
                resultado[tipo][f"init_value_{tipo}"] += v
    return {t: dict(vals) for t, vals in resultado.items()}


# ============================
# Paso 7: Ejecución principal del motor (MAIN)
# ============================

def run_motor(payload):
    
    # 7.1 – Insumos COPRO 
    datos_copro, chat_input, copro_raw = paso0_leer_input_y_decidir(payload)
    # 7.2 – Procesar Experian 
    response_exp = obtener_response_experian(chat_input)
    acum_exp, score_exp, delin_exp = procesar_response(response_exp, {})
    print("\n==============================")
    print("==== DEBUG: EXPERIAN RAW DATA ====")
    print("==============================")
    print(json.dumps(acum_exp, indent=2, ensure_ascii=False))
    print(f"\nCredit Score Experian: {score_exp}")
    print(json.dumps(delin_exp, indent=2, ensure_ascii=False))
    # 7.3 – Procesar TransUnion (Paso 2)
    response_tu = obtener_response_transunion(chat_input)
    # 7.3.1 – Procesar Experian Ingresos (RAW)
    try:
        ingresos_raw = obtener_response_ingreso_experian(chat_input)
    except Exception as e:
        ingresos_raw = {"error": str(e)}

    info_ingreso = procesar_response_ingreso_experian(ingresos_raw)

    
    acum_tu, score_tu, delin_tu = procesar_response_transunion(response_tu)
    print("\n==============================")
    print("==== DEBUG: TRANSUNION RAW DATA ====")
    print("==============================")
    print(json.dumps(acum_tu, indent=2, ensure_ascii=False))
    print(f"\nCredit Score TransUnion: {score_tu}")
    print(json.dumps(delin_tu, indent=2, ensure_ascii=False))

    # 7.4 – Vector global de moras máximas 
    todas_moras = []
    for entidad, lista in delin_exp.items():
        todas_moras.extend(lista)
    for entidad, lista in delin_tu.items():
        todas_moras.extend(lista)

    moras_maximas = calcular_vector_moras_maximas(todas_moras)

    print("\n==============================")
    print("==== VECTOR DE MORAS MÁXIMAS GLOBAL ====")
    print("==============================")
    print(json.dumps(moras_maximas, indent=2, ensure_ascii=False))


    # 7.5 – Política mora externa 12M 
    mora_ext_12m, cumple_mora_ext_12m = evaluar_politica_mora_externa_12m(moras_maximas)

    print("\n==============================")
    print("==== POLÍTICA MORA EXTERNA 12M ====")
    print("==============================")
    print(f"Peor mora 12M (global externa): {mora_ext_12m}")
    print(f"Cumple_mora_ext_12m (1=cumple, 2=no cumple): {cumple_mora_ext_12m}")


    # 7.6 – Totales globales por tipo de crédito 
    merge_global = {}
    for entidad, vals in acum_exp.items():
        merge_global[entidad] = vals.copy()
    for entidad, vals in acum_tu.items():
        if entidad in merge_global:
            for k, v in vals.items():
                merge_global[entidad][k] = merge_global[entidad].get(k, 0) + v
        else:
            merge_global[entidad] = vals.copy()

    totales_globales = agregar_por_tipo_credito_global_desde_filtrado(merge_global)

    print("\n==============================")
    print("==== TOTALES GLOBALES POR TIPO DE CRÉDITO ====")
    print("==============================")
    print(json.dumps(totales_globales, indent=2, ensure_ascii=False))


    # ============================
    # 7.7 – Cálculo de deuda externa consolidada
    # ============================
    
    def sumar_saldos(acumulador):
        """Suma todos los saldos (bal_..._ext) de un acumulador."""
        total = 0.0
        for entidad, variables in acumulador.items():
            for k, v in variables.items():
                if k.startswith("bal_") and k.endswith("_ext"):
                    total += v
        return total
    def sumar_cuotas(acumulador):
        """Suma todas las cuotas/pagos mensuales externos (ext_installment_*).

        - Experian: se construyen en `procesar_response()` desde `valueMonthlyPayment`.
        - TransUnion: se construyen en `procesar_response_transunion()` desde `ValorCuota` (solo al día).
        """
        total = 0.0
        for entidad, variables in acumulador.items():
            for k, v in variables.items():
                if k.startswith("ext_installment_"):
                    total += v
        return total

    # Totales individuales por fuente (SALDOS)
    deuda_externa_experian = sumar_saldos(acum_exp)
    deuda_externa_trans_u = sumar_saldos(acum_tu)
    
    # NUEVO: Obligaciones financieras por Experian usando CUOTAS (valueMonthlyPayment)
    cuota_experian = sumar_cuotas(acum_exp)
    cuota_trans_u = sumar_cuotas(acum_tu)

    # Obligaciones financieras (mensual) = max entre cuotas Experian y TU
    obligaciones_financieras = max(cuota_experian, cuota_trans_u)

    resumen_deuda = {
        "deuda_externa_experian": deuda_externa_experian,
        "deuda_externa_trans_u": deuda_externa_trans_u,
        "cuota_experian": cuota_experian,
        "cuota_trans_u": cuota_trans_u,
        "Obligaciones_Financieras": obligaciones_financieras
    }
    
    print("\n==============================")
    print("==== RESUMEN DE DEUDA EXTERNA ====")
    print("==============================")
    print(json.dumps(resumen_deuda, indent=2, ensure_ascii=False))
    
    # --------------------------------------------------------
    # 7.8 – Calcular ingreso total y continuidad laboral (Paso 4)
    # --------------------------------------------------------
    diccionario_temp = {
            "chat_input": chat_input,
            "Motor want": {},
            "resumen_final": {}
        }
    
    diccionario_temp = calcular_ingreso_total(diccionario_temp, info_ingreso=info_ingreso)
    ingreso_total = diccionario_temp["resumen_final"]["Ingreso_Total"]
    
    
    # --------------------------------------------------------
    # 7.9 – Resumen financiero final
    # # --------------------------------------------------------
    resumen_final = {
            "score_expe": score_exp,
            "score_trans": score_tu,
            "deuda_externa_experian": deuda_externa_experian,
            "deuda_externa_trans_u": deuda_externa_trans_u,
            "cuota_experian": cuota_experian,
            "cuota_trans_u": cuota_trans_u,
            "Ingreso_Total": ingreso_total,
            "Ingreso_Nómina_básico": ingreso_total,
            "Obligaciones_Financieras": obligaciones_financieras,
            "mora_ext_max_12m": mora_ext_12m,
        }
    
    print("\n==============================")
    print("==== RESUMEN FINANCIERO FINAL ====")
    print("==============================")
    print(json.dumps(resumen_final, indent=2, ensure_ascii=False))
    
    
    # --------------------------------------------------------
    # 7.10 – Construcción de diccionario maestro final
    # --------------------------------------------------------
    inputs_adicionales = {}
    for nombre, ruta in archivos_inputs.items():
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    inputs_adicionales[nombre] = json.load(f)
            except Exception as e:
                print(f"[ERROR] No se pudo cargar {nombre}: {e}")
    
    inputs_adicionales["COPRO"] = datos_copro
    
    diccionario_maestro = {
            "chat_input": chat_input,
            "resumen_final": resumen_final,
            "inputs_adicionales": inputs_adicionales
        }
    
    print("\n==============================")
    print("==== DICCIONARIO MAESTRO UNIFICADO ====")
    print("==============================")
    print(json.dumps(diccionario_maestro, indent=2, ensure_ascii=False))
    
    
    # ============================
    # Paso 8: Motor WANT – Cálculos internos y decisión
    # ============================
    
    # 8.1 – Edad del asociado (desde COPRO)
    
    
    def calcular_edad(diccionario_maestro):
        """
        Calcula la edad (en años y días) a partir de la fecha de nacimiento
        proveniente únicamente de la API de Coprocenva.
        Inserta los resultados en la sección 'Motor want'.
        """
    
        def dias360(fecha_inicio, fecha_fin):
            """Diferencia de días con base 30/360 (método Excel)."""
            d1, d2 = fecha_inicio.day, fecha_fin.day
            m1, m2 = fecha_inicio.month, fecha_fin.month
            y1, y2 = fecha_inicio.year, fecha_fin.year
            if d1 == 31:
                d1 = 30
            if d2 == 31 and d1 == 30:
                d2 = 30
            return (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)
    
        try:
            # 🔥 Solo se usa la fecha que viene desde COPRO (API)
            fec_nac_str = diccionario_maestro["inputs_adicionales"]["COPRO"]["fecha_nacimiento"]
    
            if not fec_nac_str:
                raise ValueError("fecha_nacimiento no encontrada en inputs_adicionales['COPRO']")
    
            # Convertir a datetime (formato esperado: YYYY-MM-DD)
            fec_nac = datetime.strptime(fec_nac_str, "%Y-%m-%d")
            hoy = datetime.today()
    
            total_dias = dias360(fec_nac, hoy)
            edad_anios = total_dias // 360
            edad_dias = total_dias - (edad_anios * 360)
    
            # Crear o actualizar sección "Motor want"
            if "Motor want" not in diccionario_maestro:
                diccionario_maestro["Motor want"] = {}
    
            diccionario_maestro["Motor want"]["edad_anios"] = edad_anios
            diccionario_maestro["Motor want"]["edad_dias"] = edad_dias
    
            print(f"✅ Edad calculada: {edad_anios} año(s) y {edad_dias} día(s)")
    
        except Exception as e:
            print(f"⚠️ Error al calcular la edad: {e}")
    
            if "Motor want" not in diccionario_maestro:
                diccionario_maestro["Motor want"] = {}
    
            diccionario_maestro["Motor want"]["edad_anios"] = ""
            diccionario_maestro["Motor want"]["edad_dias"] = ""
    
        return diccionario_maestro
    
        
    # 8.1 – Antigüedad del asociado (desde COPRO)
    
    from datetime import datetime
    
    
    def calcular_antiguedad(diccionario_maestro):
        """
        Calcula la antigüedad (en años y días) a partir de 'fecha_ingreso_coop' que
        viene de la API de Coprocenva (sección COPRO en inputs_adicionales).
        Inserta los resultados en la sección 'Motor want'.
        """
    
        def dias360(fecha_inicio, fecha_fin):
            """Diferencia de días con base 30/360 (método Excel)."""
            d1, d2 = fecha_inicio.day, fecha_fin.day
            m1, m2 = fecha_inicio.month, fecha_fin.month
            y1, y2 = fecha_inicio.year, fecha_fin.year
            if d1 == 31:
                d1 = 30
            if d2 == 31 and d1 == 30:
                d2 = 30
            return (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)
    
        try:
            # 🔥 Nueva fuente: COPRO (API normalizada), ya no BD_COOP
            fec_ing_str = diccionario_maestro["inputs_adicionales"]["COPRO"]["fecha_ingreso_coop"]
    
            if not fec_ing_str:
                raise ValueError("fecha_ingreso_coop vacía en inputs_adicionales['COPRO']")
    
            # Formato esperado: 'YYYY-MM-DD'
            fec_ing = datetime.strptime(fec_ing_str, "%Y-%m-%d")
            hoy = datetime.today()
    
            # Calcular antigüedad total en días base 360
            total_dias = dias360(fec_ing, hoy)
            antig_anios = total_dias // 360
            antig_dias = total_dias - (antig_anios * 360)
    
            # Crear o actualizar sección "Motor want"
            if "Motor want" not in diccionario_maestro:
                diccionario_maestro["Motor want"] = {}
    
            diccionario_maestro["Motor want"]["antig_anios"] = antig_anios
            diccionario_maestro["Motor want"]["antig_dias"] = antig_dias
    
            print(f"✅ Antigüedad calculada: {antig_anios} año(s) y {antig_dias} día(s)")
    
        except Exception as e:
            print(f"⚠️ Error al calcular la antigüedad: {e}")
            if "Motor want" not in diccionario_maestro:
                diccionario_maestro["Motor want"] = {}
    
            diccionario_maestro["Motor want"]["antig_anios"] = ""
            diccionario_maestro["Motor want"]["antig_dias"] = ""
    
        return diccionario_maestro
    
    # 8.2 – Generación del número de radicación y fecha de radicación
    
    def generar_datos_radicacion(diccionario_maestro):
        """
        Genera:
          - n_radicacion: ID_AAMMDDHHmmss  (año con 2 dígitos)
          - fecha_radicacion: AAAAMMDDHHmmss (año con 4 dígitos)
        usando:
          - ID desde diccionario_maestro["chat_input"]["id"]
          - Fecha/hora actual en zona horaria Colombia (UTC-5)
        y los guarda en diccionario_maestro["Motor want"].
        """
    
        chat_input = diccionario_maestro.get("chat_input", {}) or {}
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        # ID desde el chat_input
        person_id = str(chat_input.get("id", "") or "")
    
        # Fecha/hora Colombia (UTC-5)
        now_col = datetime.now(timezone(timedelta(hours=-5)))
    
        # AAMMDDHHmmss (2 dígitos de año)
        sufijo_aammddhhmmss = now_col.strftime("%y%m%d%H%M%S")
    
        # AAAAMMDDHHmmss (4 dígitos de año)
        fecha_aaaammddhhmmss = now_col.strftime("%Y%m%d%H%M%S")
    
        # Construir n_radicacion = ID_AAMMDDHHmmss
        if person_id:
            n_radicacion = f"{person_id}_{sufijo_aammddhhmmss}"
        else:
            n_radicacion = f"NA_{sufijo_aammddhhmmss}"
    
        motor["n_radicacion"] = n_radicacion
        motor["fecha_radicacion"] = fecha_aaaammddhhmmss
    
        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    # 8.3 – Parámetro de campaña: Nueva Vida
    
    def calcular_nueva_vida(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        # Leer variable fuente
        nueva_vida = motor.get("nueva_vida", "")
    
        # Aplicar lógica
        if str(nueva_vida).upper() == "SI":
            nueva_vida_especial = "NUEVA POLIZA"
        else:
            nueva_vida_especial = 0
    
        # Guardar resultado
        motor["nueva_vida_especial"] = nueva_vida_especial
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    
    # 8.4 – Tasa mensual del seguro
    
    def calcular_tasa_men_seguro(diccionario_maestro):
        """
        Tasa de seguro fija: 0.03000% mensual (0.0003000 decimal)
        Ajustada por extraprima si aplica.
        """
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        extraprima = motor.get("extraprima", 0)
    
        # Tasa única ajustada por extraprima
        tasa_base = 0.0003000
        tasa_men_seguro = tasa_base * (1 + extraprima)
    
        # Guardar resultado
        motor["tasa_men_seguro"] = tasa_men_seguro
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.4 – Tasa anual equivalente del seguro
    
    def calcular_tasa_anual(diccionario_maestro):
        """
        Calcula la tasa anual equivalente a partir de la tasa mensual de seguro.
        Fórmula Excel: SI(F13<>0;((1+F22)^12)-1;"")
        """
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        edad_anios = motor.get("edad_anios", 0)
        tasa_men_seguro = motor.get("tasa_men_seguro", 0)
    
        if isinstance(tasa_men_seguro, (int, float)) and edad_anios != 0:
            tasa_anual = ((1 + tasa_men_seguro) ** 12) - 1
        else:
            tasa_anual = ""
    
        motor["tasa_anual"] = tasa_anual
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.5 – Línea_concat (modalidad + destino)
    
    def calcular_linea_concat(diccionario_maestro):
        """
        Concatena las variables modalidad y destino para formar Línea_concat.
        Fórmula Excel: CONCAT(F31;F32)
        """
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        modalidad = motor.get("modalidad_motor", "")
        destino = motor.get("destino_motor", "")
    
        # Convertimos ambos valores a texto para evitar errores de tipo
        linea_concat = f"{str(modalidad)}{str(destino)}"
    
        motor["Línea_concat"] = linea_concat
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.6 – Tasa nominal mes vencido (FIJA)

    def calcular_tasa_nominal_mes_vencido(diccionario_maestro):
        """Tasa única vigente para este crédito: 1.86% mes vencido."""

        motor = diccionario_maestro.setdefault("Motor want", {})

        # 1.86% MV en formato decimal (0.0186)
        motor["Tasa_Nominal_Mes_Vencido"] = 0.0186

        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    # 8.6 – Cálculo de cuota (incluye seguro)
    
    def calcular_cuota_incluye_el_seguro(diccionario_maestro):
        """
        Calcula la Cuota_Incluye_el_seguro según la fórmula Excel:
            =SI.ERROR(SI(F36="NO APLICA CAMPAÑA POR PLAZO";"RECHAZADO";PAGO(F36+F22;F35;-F30));"")
        
        Usa numpy_financial.pmt() para replicar la función PAGO de Excel.
        """
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        tasa_nominal = motor.get("Tasa_Nominal_Mes_Vencido", "")
        tasa_seguro = motor.get("tasa_men_seguro", 0)
        plazo_cuotas = motor.get("plazo_cuotas", 0)
        monto_credito = motor.get("Monto_Crédito", 0)
    
        try:
            # Caso especial: no aplica campaña
            if str(tasa_nominal).upper() == "NO APLICA CAMPAÑA POR PLAZO":
                cuota = "RECHAZADO"
    
            # Si hay tasa numérica válida, calcular PAGO
            elif isinstance(tasa_nominal, (int, float)):
                tasa_total = tasa_nominal + tasa_seguro
                cuota = npf.pmt(tasa_total, plazo_cuotas, -monto_credito)
                cuota = round(float(cuota), 2)  # redondear a 2 decimales
    
            else:
                cuota = ""
    
        except Exception:
            cuota = ""
    
        # Guardar en el motor
        motor["Cuota_Incluye_el_seguro"] = cuota
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    
    # 8.7 – Cuota mensual por estatutarios
    
    def calcular_cuota_mensual_estatutarios(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        resumen = diccionario_maestro.get("resumen_final", {})
        ingreso_total = resumen.get("Ingreso_Total", "")
    
        try:
            if ingreso_total in ("", None):
                cuota = 0
            elif ingreso_total <= 2_626_358:
                cuota = 59_600
            elif 2_626_359 <= ingreso_total <= 5_252_715:
                cuota = 81_700
            elif ingreso_total > 5_252_715:
                cuota = 103_800
            else:
                cuota = 0
        except Exception:
            cuota = 0
    
        motor["Cuota_Mensual_Estatutarios"] = cuota
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.7 – Gastos familiares según ingreso
    
    def calcular_gastos_familiares(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
        resumen = diccionario_maestro.get("resumen_final", {})
    
        ingreso_total = resumen.get("Ingreso_Total", 0)
        SMMLV = 1_750_905  # Salario Mínimo Mensual Legal Vigente 2026
    
        try:
            if ingreso_total < (8 * SMMLV):
                gastos_familiares = ingreso_total * 0.30
            else:
                gastos_familiares = ingreso_total * 0.20
        except Exception:
            gastos_familiares = 0
    
        motor["Gastos_Familiares"] = gastos_familiares
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.7 – Neto parcial
    
    def calcular_neto_parcial(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
        resumen = diccionario_maestro.get("resumen_final", {})
    
        ingreso_total = resumen.get("Ingreso_Total", 0)
        gastos_familiares = motor.get("Gastos_Familiares", 0)
    
        try:
            neto_parcial = ingreso_total - gastos_familiares
        except Exception:
            neto_parcial = 0
    
        motor["Neto_parcial"] = neto_parcial
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.7 – Neto final
    
    def calcular_neto_final(diccionario_maestro):
        """
        Calcula el Neto_final según la fórmula:
            = Neto_parcial - Descuentos_no_bancarios - Obligaciones_Financieras
    
        Donde:
            Neto_parcial → Motor want
            Descuentos_no_bancarios → Motor want
            Obligaciones_Financieras → resumen_final
        """
    
        motor = diccionario_maestro.setdefault("Motor want", {})
        resumen = diccionario_maestro.get("resumen_final", {})
    
        neto_parcial = motor.get("Neto_parcial", 0)
        descuentos_no_bancarios = motor.get("Descuentos_no_bancarios", 0)
        obligaciones_financieras = resumen.get("Obligaciones_Financieras", 0)
    
        try:
            neto_final = neto_parcial - descuentos_no_bancarios - obligaciones_financieras
        except Exception:
            neto_final = 0
    
        motor["Neto_final"] = neto_final
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.7 – Capacidad de pago y cumplimiento de política
    
    # --- Capacidad_de_pago ---
    
    def calcular_capacidad_de_pago(diccionario_maestro):
        """
        Calcula la Capacidad_de_pago según la fórmula Excel:
            =SI.ERROR(F57/F37; "")
        
        Donde:
            F57 → Neto_final (Motor want)
            F37 → Cuota_Incluye_el_seguro (Motor want)
        """
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        neto_final = motor.get("Neto_final", 0)
        cuota_incluye_seguro = motor.get("Cuota_Incluye_el_seguro", 0)
    
        try:
            if cuota_incluye_seguro == 0:
                capacidad_pago = ""
            else:
                capacidad_pago = neto_final / cuota_incluye_seguro
        except Exception:
            capacidad_pago = ""
    
        motor["Capacidad_de_pago"] = capacidad_pago
    
        # --- Validación contra el mínimo requerido (1.3) ---
        minimo = 1.3
    
        if isinstance(capacidad_pago, (int, float)) and capacidad_pago != "":
            if capacidad_pago >= minimo:
                motor["Cumple_capacidad_pago"] = 1
            else:
                motor["Cumple_capacidad_pago"] = 2
        else:
            # Si no hay dato válido → incumple
            motor["Cumple_capacidad_pago"] = 2
    
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.8 – Deducciones de ley (8%)
    
    # --- Deducciones_Ley ---
 
    def calcular_deducciones_ley(diccionario_maestro):
        """
        Calcula Deducciones_Ley según tabla (8% / 9%) y
        deja Descuentos_no_bancarios IGUAL al mismo valor (sin cambiar nombres).

        Tabla:
        - base <= 7,003,620.00 -> 8%
        - base  > 7,003,620.00 -> 9%

        Base (orden):
        1) Ingreso_Nómina_básico (si es numérico)
        2) Ingreso_Total (si es numérico)
        3) 0
        """

        motor = diccionario_maestro.setdefault("Motor want", {})
        resumen = diccionario_maestro.get("resumen_final", {}) or {}

        ingreso_nomina = resumen.get("Ingreso_Nómina_básico")
        ingreso_total = resumen.get("Ingreso_Total") or resumen.get("Ingreso_total")

        # Elegimos la base correcta
        if isinstance(ingreso_nomina, (int, float)):
            base = float(ingreso_nomina)
        elif isinstance(ingreso_total, (int, float)):
            base = float(ingreso_total)
        else:
            base = 0.0

        # Umbral y porcentaje según tabla
        UMBRAL_8 = 7_003_620.00
        porcentaje = 0.08 if base <= UMBRAL_8 else 0.09

        deducciones_ley = base * porcentaje

        # Guardar ambos campos iguales (sin cambiar nombres)
        motor["Deducciones_Ley"] = deducciones_ley
        motor["Descuentos_no_bancarios"] = deducciones_ley

        # (opcional pero útil) trazabilidad
        motor["Porcentaje_descuentos_ley"] = porcentaje

        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    
    # 8.8 – Disponible para descuento por nómina
    
    def calcular_disponible_descuento(diccionario_maestro):
        """
        Calcula el Disponible_descuento según la fórmula Excel:
            =SI(SI(F60/2<1750905;F60-1750905-F61-F62;((F60-F61)/2)-F62)<=0;0;
                SI(F60/2<1750905;F60-1750905-F61-F62;((F60-F61)/2)-F62))
    
        Donde:
            F60 → Ingreso_Nómina_básico (resumen_final)
            F61 → Deducciones_Ley (Motor want o resumen_final)
            F62 → Otras_deducciones_nómina (chat_input)
            SMMLV = 1_750_905
        """
    
        resumen = diccionario_maestro.get("resumen_final", {})
        motor = diccionario_maestro.setdefault("Motor want", {})
        chat = diccionario_maestro.get("chat_input", {})
    
        ingreso_basico = resumen.get("Ingreso_Nómina_básico", 0)
        deducciones_ley = motor.get("Deducciones_Ley", resumen.get("Deducciones_Ley", 0))
        otras_deducciones = chat.get("Otras_deducciones_nómina", 0)
    
        SMMLV = 1_750_905  # Salario mínimo vigente 2026
    
        try:
            if (ingreso_basico / 2) < SMMLV:
                disponible = ingreso_basico - SMMLV - deducciones_ley - otras_deducciones
            else:
                disponible = ((ingreso_basico - deducciones_ley) / 2) - otras_deducciones
    
            if disponible <= 0:
                disponible = 0
        except Exception:
            disponible = 0
    
        resumen["Disponible_descuento"] = disponible
        diccionario_maestro["resumen_final"] = resumen
    
        return diccionario_maestro
    
    # 8.9 – Cálculo del monto perfilado
    
    def valor_actual(tasa, n_periodos, pago, vf=0, tipo=0):
        
        if tasa == 0:
            return -(pago * n_periodos + vf)
        else:
            return -((pago * (1 + tasa * tipo) * (1 - (1 + tasa) ** (-n_periodos))) / tasa + vf)
    
    
    import math
    
    def calcular_monto_perfilado(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        tasa_nominal = motor.get("Tasa_Nominal_Mes_Vencido", 0)
        tasa_seguro = motor.get("tasa_men_seguro", 0)
        plazo_meses = motor.get("plazo_meses", 0)
        neto_final = motor.get("Neto_final", 0)
    
        try:
            tasa_total = tasa_nominal + tasa_seguro
            pago = -neto_final / 1.35
    
            monto = valor_actual(tasa_total, plazo_meses, pago, 0, 0)
    
            # Redondear al millón inferior
            monto_perfilado = math.floor(monto / 1_000_000) * 1_000_000
    
        except Exception:
            monto_perfilado = ""
    
        motor["monto_perfilado"] = monto_perfilado
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.10 – Cálculo del capital de riesgo
    
    def calcular_capital_riesgo(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
        copro = diccionario_maestro.get("inputs_adicionales", {}).get("COPRO", {})
    
        # Equivalencias aprobadas:
        # Endeudamiento_Coprocenva  -> saldo_capital
        # saldo_aportes (BD_COOP)   -> saldoAportes (COPRO)
        endeudamiento_coprocenva = copro.get("saldo_capital", 0) or 0
        saldo_aportes = copro.get("saldo_aportes", 0) or 0
    
        # Monto del crédito viene del motor
        monto_credito = motor.get("Monto_Crédito", 0) or 0
    
        try:
            capital_riesgo = endeudamiento_coprocenva + monto_credito - saldo_aportes
            if capital_riesgo <= 0:
                capital_riesgo = 0
        except Exception:
            capital_riesgo = 0
    
        motor["Capital_Riesgo"] = capital_riesgo
        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    # 8.10 – Total endeudamiento, nivel y pasivos
    
    def calcular_endeudamiento(diccionario_maestro):
    
        motor   = diccionario_maestro.setdefault("Motor want", {})
        resumen = diccionario_maestro.get("resumen_final", {})
        inputs  = diccionario_maestro.get("inputs_adicionales", {})
        copro   = inputs.get("COPRO", {})        # 🟢 Nueva fuente para endeudamiento_coprocenva
    
        deuda_exp = resumen.get("deuda_externa_experian", 0) or 0
        deuda_tu  = resumen.get("deuda_externa_trans_u", 0) or 0
        deuda_externa = max(deuda_exp, deuda_tu)
    
    
        # Antes: endeudamiento_coprocenva = bd_coop.get("Endeudamiento_Coprocenva", 0)
        # Endeudamiento_Coprocenva = saldoCapital (API COPRO)
        endeudamiento_coprocenva = copro.get("saldo_capital", 0) or 0
    
        monto_credito = motor.get("Monto_Crédito", 0) or 0
    
        # 🔸 AÚN NO MIGRADO: sigue leyendo de BD_COOP hasta que definan el campo en COPRO
        credito_hipotecario = copro.get("deuda_vivienda_coop", 0) or 0
    
        try:
            total_endeudamiento = deuda_externa + endeudamiento_coprocenva + monto_credito
            nivel_endeudamiento = total_endeudamiento - credito_hipotecario
            pasivos = monto_credito + endeudamiento_coprocenva + deuda_externa
        except Exception:
            total_endeudamiento = 0
            nivel_endeudamiento = 0
            pasivos = 0
    
        motor["Total_endeudamiento"] = total_endeudamiento
        motor["Nivel_endeudamiento"] = nivel_endeudamiento
        motor["Pasivos"] = pasivos
    
        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    # 8.10 – Solvencia y endeudamiento (política)
    
    # --- Solvencia ---
    # --- Endeudamiento ---
    
    def calcular_solvencia_endeudamiento(diccionario_maestro):
    
        motor  = diccionario_maestro.setdefault("Motor want", {})
        inputs = diccionario_maestro.get("inputs_adicionales", {})

        copro = inputs.get("COPRO", {}) or {}
        chat_input = diccionario_maestro.get("chat_input", {}) or {}

        # Fuente 1: Activos desde API Copro (ya normalizado)
        activos_api = _to_float_money(copro.get("valor_activos"))

        # Fuente 2: Activos desde Chat Input
        activos_chat = _to_float_money(chat_input.get("activos"))

        # Regla: usar el máximo entre ambas fuentes
        valor_activos = max(activos_api, activos_chat)

        # (Recomendado) trazabilidad para auditoría
        motor["Activos_api_copro"] = activos_api
        motor["Activos_chat_input"] = activos_chat
        motor["Activos_final"] = valor_activos
    

        pasivos = motor.get("Pasivos", 0) or 0
    
        # Solvencia = Activos / Pasivos
        try:
            solvencia = valor_activos / pasivos if pasivos != 0 else 0
        except Exception:
            solvencia = 0
        motor["Solvencia"] = solvencia
    
        # --- Validación de política: solvencia mínima 1 ---
        minimo = 1
    
        if isinstance(solvencia, (int, float)):
            if solvencia >= minimo:
                motor["Cumple_solvencia"] = 1
            else:
                motor["Cumple_solvencia"] = 2
        else:
            # Solvencia inválida → incumple
            motor["Cumple_solvencia"] = 2
    
        # Endeudamiento = Pasivos / Activos
        try:
            endeudamiento = pasivos / valor_activos if valor_activos > 0 else 0
        except Exception:
            endeudamiento = 0
    
        motor["Endeudamiento"] = endeudamiento
    
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.11 – Liquidez del asociado y tiempos Taylor (radicación, recepción, análisis)
    
    # --- Liquidez ---
    # --- TIEMPO_RECEP ---
    # --- TIEMPO_ANAL ---
    
    from datetime import datetime
    
    def calcular_liquidez_y_tiempos(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
        taylor = diccionario_maestro.get("inputs_adicionales", {}).get("TAYLOR", {})
    
        # === LIQUIDEZ ===
        motor["Liquidez"] = motor.get("Neto_final", 0)
    
        # === FECHAS ===
        try:
            fecha_radic = datetime.strptime(taylor.get("FECHA_RADICACIÓN_SBI", ""), "%Y-%m-%d")
            fecha_recep = datetime.strptime(taylor.get("FECHA_RECEPCIÓN_ANALISIS", ""), "%Y-%m-%d")
            fecha_anal = datetime.strptime(taylor.get("FECHA_ANÁLISIS", ""), "%Y-%m-%d")
    
            tiempo_recep = (fecha_recep - fecha_radic).days
            tiempo_anal = (fecha_anal - fecha_recep).days
    
        except Exception:
            tiempo_recep = 0
            tiempo_anal = 0
    
        motor["TIEMPO_RECEP"] = tiempo_recep
        motor["TIEMPO_ANAL"] = tiempo_anal
        diccionario_maestro["Motor want"] = motor
    
        return diccionario_maestro
    
    # 8.12 asegurabilidad 
    
    def calcular_asegurabilidad(diccionario_maestro):
    
        motor = diccionario_maestro.setdefault("Motor want", {})
        copro = diccionario_maestro.get("inputs_adicionales", {}).get("COPRO", {})
    
        monto_credito = motor.get("Monto_Crédito", 0) or 0
        endeudamiento_coprocenva = copro.get("saldo_capital", 0) or 0
        edad_anios = motor.get("edad_anios", 0) or 0
    
        try:
            # Criterios de asegurabilidad
            if (monto_credito + endeudamiento_coprocenva) > 100_000_000 or edad_anios > 70:
                asegurabilidad = "REVISAR ASEGURABILIDAD"
            else:
                asegurabilidad = ""
        except Exception:
            asegurabilidad = ""
    
        motor["asegurabilidad"] = asegurabilidad
        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    # 8.12 – Decisión final del Motor Want
    
    def evaluar_decision_final(diccionario_maestro):
        motor = diccionario_maestro.setdefault("Motor want", {})
    
        # Tomar todas las variables que empiezan con "Cumple_"
        cumple_vars = [v for k, v in motor.items() if k.startswith("Cumple_")]
    
        # Evaluación global
        if cumple_vars and all(v == 1 for v in cumple_vars):
            motor["motor_2"] = 1
            motor["Decision_final"] = "CUMPLE POLÍTICA DE CRÉDITO"
        else:
            motor["motor_2"] = 2
            motor["Decision_final"] = "NO CUMPLE POLÍTICA DE CRÉDITO"
    
        diccionario_maestro["Motor want"] = motor
        return diccionario_maestro
    
    
    # ============================================================
    # Paso 9: Construcción del Output Final del Motor Want
    # ============================================================
    
    # ------------------------------------------------------------
    # 9.0 – Normalización (llaves: minusculas, sin tildes, con _)
    # ------------------------------------------------------------
    import unicodedata
    import re
    
    def normalize_key(key: str) -> str:
        key = unicodedata.normalize("NFKD", str(key))
        key = "".join(c for c in key if not unicodedata.combining(c))
        key = key.lower()
        key = re.sub(r"\s+", "_", key)
        key = re.sub(r"[^a-z0-9_]", "", key)
        key = re.sub(r"_+", "_", key).strip("_")
        return key
    
    def normalize_dict_keys(obj):
        if isinstance(obj, dict):
            return {normalize_key(k): normalize_dict_keys(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [normalize_dict_keys(x) for x in obj]
        return obj
    
    
    # ------------------------------------------------------------
    # 9.1 – Variables base y tabla de plazos por monto
    # ------------------------------------------------------------
    motor = diccionario_maestro.setdefault("Motor want", {})
    
    TABLA_PLAZO_MONTO = [
        {"min": 1_000_000,   "max": 2_000_000,   "plazo": 12},
        {"min": 2_000_001,   "max": 3_000_000,   "plazo": 24},
        {"min": 3_000_001,   "max": 4_000_000,   "plazo": 30},
        {"min": 4_000_001,   "max": 5_000_000,   "plazo": 32},
        {"min": 5_000_001,   "max": 6_000_000,   "plazo": 25},
        {"min": 6_000_001,   "max": 7_000_000,   "plazo": 40},
        {"min": 7_000_001,   "max": 8_000_000,   "plazo": 42},
        {"min": 8_000_001,   "max": 9_000_000,   "plazo": 45},
        {"min": 9_000_001,   "max": 11_000_000,  "plazo": 48},
        {"min": 11_000_001,  "max": 14_000_000,  "plazo": 54},
    ]
    
    def obtener_plazo_por_monto(monto):
        for fila in TABLA_PLAZO_MONTO:
            if fila["min"] <= monto <= fila["max"]:
                return fila["plazo"]
        return 54
    
    
    # ------------------------------------------------------------
    # 9.2 – Asignación de parámetros base del crédito
    # ------------------------------------------------------------
    motor.setdefault("extraprima", 0)
    motor.setdefault("no_asegurables", "SI")
    
    # --- Normalizar monto (Hibot lo manda como string) ---
    req_amount_raw = chat_input.get("req_amount", 0)
    try:
       if isinstance(req_amount_raw, str):
        req_amount_raw = (
            req_amount_raw.strip()
            .replace("$", "")
            .replace(" ", "")
            .replace(".", "")
            .replace(",", "")
        )
       motor["Monto_Crédito"] = int(float(req_amount_raw or 0))
    except (TypeError, ValueError):
     return {"status": "error", "message": f"req_amount inválido: {chat_input.get('req_amount')}"}
    
    monto = motor["Monto_Crédito"]
    
    motor.setdefault("nueva_vida", "SI")
    motor.setdefault("modalidad_motor", 1)
    motor.setdefault("destino_motor", 72)
    
    plazo_meses = obtener_plazo_por_monto(monto)
    motor["plazo_meses"] = plazo_meses
    motor["plazo_cuotas"] = plazo_meses
    motor["Agencia_de_desembolso"] = chat_input.get("agencia", "")

    
    
    
    # ------------------------------------------------------------
    # 9.3 – Ejecutar en orden todos los cálculos previos del Motor Want (Paso 8)
    # ------------------------------------------------------------
    diccionario_maestro = generar_datos_radicacion(diccionario_maestro)
    diccionario_maestro = calcular_edad(diccionario_maestro)
    diccionario_maestro = calcular_antiguedad(diccionario_maestro)
    diccionario_maestro = calcular_nueva_vida(diccionario_maestro)
    diccionario_maestro = calcular_tasa_men_seguro(diccionario_maestro)
    diccionario_maestro = calcular_tasa_anual(diccionario_maestro)
    diccionario_maestro = calcular_linea_concat(diccionario_maestro)
    diccionario_maestro = calcular_tasa_nominal_mes_vencido(diccionario_maestro)
    diccionario_maestro = calcular_cuota_incluye_el_seguro(diccionario_maestro)
    diccionario_maestro = calcular_ingreso_total(diccionario_maestro, info_ingreso=info_ingreso)
    diccionario_maestro = calcular_cuota_mensual_estatutarios(diccionario_maestro)
    
    # Variables de moras externas provenientes del Paso 7
    diccionario_maestro["Motor want"]["mora_ext_12m"] = mora_ext_12m
    diccionario_maestro["Motor want"]["Cumple_mora_ext_12m"] = cumple_mora_ext_12m
    
    diccionario_maestro = evaluar_politica_score_minimo(diccionario_maestro, score_exp, score_tu)
    diccionario_maestro = calcular_capital_riesgo(diccionario_maestro)
    diccionario_maestro = calcular_asegurabilidad(diccionario_maestro)
    diccionario_maestro = calcular_gastos_familiares(diccionario_maestro)
    diccionario_maestro = calcular_neto_parcial(diccionario_maestro)
    diccionario_maestro = calcular_deducciones_ley(diccionario_maestro)
    diccionario_maestro = calcular_neto_final(diccionario_maestro)
    diccionario_maestro = calcular_capacidad_de_pago(diccionario_maestro)
    diccionario_maestro = calcular_disponible_descuento(diccionario_maestro)
    diccionario_maestro = calcular_monto_perfilado(diccionario_maestro)
    diccionario_maestro = calcular_endeudamiento(diccionario_maestro)
    diccionario_maestro = calcular_solvencia_endeudamiento(diccionario_maestro)
    diccionario_maestro = calcular_liquidez_y_tiempos(diccionario_maestro)
    diccionario_maestro = evaluar_decision_final(diccionario_maestro)
    
    
    # ------------------------------------------------------------
    # 9.4 – Corrección de ingreso y preparación del resumen
    # ------------------------------------------------------------
    # output_file = os.path.join(base_path, "motor_output.json")
    
    motor = diccionario_maestro.get("Motor want", {}) or {}
    resumen = diccionario_maestro.get("resumen_final", {}) or {}
    chat_input = diccionario_maestro.get("chat_input", {}) or {}
    inputs_adicionales = diccionario_maestro.get("inputs_adicionales", {}) or {}
    copro = inputs_adicionales.get("COPRO", {}) or {}
    
    ing_total = resumen.get("Ingreso_Total")
    if isinstance(ing_total, (int, float)):
        resumen["Ingreso_Nómina_básico"] = ing_total
    diccionario_maestro["resumen_final"] = resumen
    
    
    # ------------------------------------------------------------
    # 9.5 – Ordenamiento del Motor Want (detallado)
    # ------------------------------------------------------------
    ordered_motor_keys = [
        "n_radicacion", "fecha_radicacion", "motor_2", "Monto_Crédito",
        "plazo_meses", "plazo_cuotas", "modalidad_motor", "destino_motor","Agencia_de_desembolso", "Línea_concat",
    
        "edad_anios", "edad_dias", "antig_anios", "antig_dias",
    
        "no_asegurables", "nueva_vida", "nueva_vida_especial",
        "extraprima", "tasa_men_seguro", "tasa_anual",
    
        "Ingreso_total", "Meses_continuidad",
    
        "Tasa_Nominal_Mes_Vencido", "Cuota_Incluye_el_seguro",
        "Cuota_Mensual_Estatutarios",
    
        "Gastos_Familiares", "Deducciones_Ley",
        "Descuentos_no_bancarios", "Neto_parcial", "Neto_final",
        "Capacidad_de_pago",
    
        "Capital_Riesgo", "Total_endeudamiento", "Nivel_endeudamiento",
        "Pasivos", "Solvencia", "Endeudamiento", "Liquidez",
        "asegurabilidad",
    
        "mora_ext_12m", "Score_minimo_buro",
        "TIEMPO_RECEP", "TIEMPO_ANAL", "monto_perfilado",
    ]
    
    motor_ordenado = {}
    
    for key in ordered_motor_keys:
        if key in motor:
            motor_ordenado[key] = motor[key]
    
    for key, val in motor.items():
        if key not in motor_ordenado and not key.startswith("Cumple_") and key != "Decision_final":
            motor_ordenado[key] = val
    
    for key, val in motor.items():
        if key.startswith("Cumple_"):
            motor_ordenado[key] = val
    
    if "Decision_final" in motor:
        motor_ordenado["Decision_final"] = motor["Decision_final"]
    
    
    # ------------------------------------------------------------
    # 9.6 – Ordenamiento del resumen final
    # ------------------------------------------------------------
    ordered_resumen_keys = [
        "score_expe", "score_trans",
        "Ingreso_declarado_asociado",
        "Ingreso_experian_promedio",
        "Ingreso_Total", "Ingreso_Nómina_básico",
        "Meses_continuidad",
        "deuda_externa_experian", "deuda_externa_trans_u",
        "Obligaciones_Financieras",
        "mora_ext_max_12m",
        "Disponible_descuento",
    ]
    
    resumen_ordenado = {}
    for key in ordered_resumen_keys:
        if key in resumen:
            resumen_ordenado[key] = resumen[key]
    for key, val in resumen.items():
        if key not in resumen_ordenado:
            resumen_ordenado[key] = val
    
    
    # ------------------------------------------------------------
    # 9.7 – Sección datos del asociado
    # ------------------------------------------------------------
    datos_asociado = {
        "id": chat_input.get("id", copro.get("id_asociado")),
        "nombre": copro.get("nombre"),
        "apellido": copro.get("apellido"),
        "celular": chat_input.get("celular"),
        "email": chat_input.get("email")
    }
    
    
    # ------------------------------------------------------------
    # 9.8 – Construcción del output final
    # ------------------------------------------------------------
    # Helpers para el cambio de formato de variables de crédito

    def fmt_pesos(valor):
        try:
            return f"${valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return ""


    def fmt_porcentaje(valor, decimales=2):
        try:
            return f"{valor * 100:.{decimales}f}%"
        except Exception:
            return ""
    # ---- motor_want resumido (mantienes tu regla previa: si motor_2 != 1 se vacía este resumen) ----
    motor_resumido = {
        "n_radicacion": motor.get("n_radicacion"),
        "fecha_radicacion": motor.get("fecha_radicacion"),
        "motor_2": motor.get("motor_2"),
        "Agencia_de_desembolso": motor.get("Agencia_de_desembolso", ""),
    }
    
    if motor.get("motor_2") == 1:
        motor_resumido.update({
            "monto_credito": fmt_pesos(motor.get("Monto_Crédito")),
            "plazo_meses": motor.get("plazo_meses"),
            "tasa_mensual_vencido": fmt_porcentaje(motor.get("Tasa_Nominal_Mes_Vencido"), 2),
            "tasa_mensual_seguro": fmt_porcentaje(motor.get("tasa_men_seguro"), 5),
            "cuota_incluye_seguro": fmt_pesos(motor.get("Cuota_Incluye_el_seguro")),
        })
    else:
        motor_resumido.update({
            "monto_credito": "",
            "plazo_meses": "",
            "tasa_mensual_vencido": "",
            "tasa_mensual_seguro": "",
            "cuota_incluye_seguro": "",
        })
    
    resumen_out = dict(resumen_ordenado)  # copia (sin vaciar)
    
    # Agregar ocupación (código) proveniente del chat_input
    resumen_out["ocupacion"] = chat_input.get("ocupacion")
    
    # Agregar ocupación (código) al detallado_want
    motor_ordenado["ocupacion"] = chat_input.get("ocupacion")
    
    # ---- output final (TODO snake_case) ----
    motor_output = {
        "datos_asociado": datos_asociado,
        "api_responses": {
            "coprocenva": copro_raw,
            "experian_hdcplus": response_exp,
            "transunion": response_tu,
            "experian_ingresos": ingresos_raw,
        },
        "resumen_final": resumen_out,
        "detallado_want": motor_ordenado,
        "motor_want": motor_resumido,
    }
    
    # Normaliza llaves de TODA la salida final
    motor_output = normalize_dict_keys(motor_output)
    
    
    # ------------------------------------------------------------
    # 9.9 – Guardar archivo motor_output.json
    # ------------------------------------------------------------
    try:
        # with open(output_file, "w", encoding="utf-8") as f:
        #     json.dump(motor_output, f, indent=4, ensure_ascii=False)
        save_json_blob_by_id(chat_input.get("id"), "motor_output.json", motor_output)
        print("\n====================================")
        print(" ARCHIVO 'motor_output.json' GENERADO ")
        print(" Ubicación:", "Blob Storage")
        print("====================================\n")
    
    except Exception as e:
            import traceback
            print("\n[ERROR] No se pudo guardar 'motor_output.json':", e)
            print(traceback.format_exc())
    return motor_output

# if __name__ == "__main__":
#     run_motor()