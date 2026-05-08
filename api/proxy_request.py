import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def proxy_request(method, url, headers=None, json_body=None,
                  timeout=30, retries=2, backoff_factor=1):
    """
    Realiza una petición HTTP enrutando el tráfico a través del egress proxy
    de Coprocenva (VM: coprocenva-egress-proxy, IP pública fija: 4.248.201.22).

    En Azure, el tráfico sale por la VNet integration hacia la IP privada
    del proxy (PROXY_HOST=10.20.1.4), que lo reenvía al exterior usando
    la IP pública estática 4.248.201.22 (en whitelist de Experian y TransUnion).

    Variables de entorno requeridas:
        PROXY_HOST  — IP privada de la VM proxy en motor-vnet (10.20.1.4)
        PROXY_PORT  — Puerto Squid en la VM (3128)
    """
    PROXY_HOST = os.environ.get("PROXY_HOST", "")
    PROXY_PORT = os.environ.get("PROXY_PORT", "3128")

    proxies = {}
    if PROXY_HOST:
        proxy_url = f"http://{PROXY_HOST}:{PROXY_PORT}"
        proxies = {
            "http":  proxy_url,
            "https": proxy_url,
        }
        print(f"[proxy_request] Usando proxy {proxy_url} para {method} {url}")
    else:
        print(f"[proxy_request] PROXY_HOST no configurado — llamada directa a {url}")

    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "PATCH"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://",  adapter)
    session.mount("https://", adapter)

    response = session.request(
        method=method,
        url=url,
        headers=headers,
        json=json_body,
        proxies=proxies,
        timeout=timeout,
        verify=True,  # Siempre verificar certificados SSL
    )
    return response
