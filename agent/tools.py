# agent/tools.py — Herramientas del agente Capitan GT
# Generado por AgentKit

"""
Herramientas específicas para Capitan GT.
Manejo de pedidos, consulta de catálogo, calificación de leads y soporte post-venta.
"""

import os
import re
import yaml
import logging
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")

# Enlace al catálogo de Capitan GT
CATALOGO_URL = "https://drive.google.com/drive/folders/1Kz7Ft62aoiBx_bq8qyBR0660MmSelN-8?usp=sharing"


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención de Capitan GT."""
    info = cargar_info_negocio()
    hora_actual = datetime.now().hour
    # Abierto de 6am a 11pm (6 a 23)
    esta_abierto = 6 <= hora_actual < 23
    return {
        "horario": info.get("negocio", {}).get("horario", "Lunes a Domingo de 6:00am a 11:00pm"),
        "esta_abierto": esta_abierto,
    }


def obtener_catalogo() -> str:
    """Retorna el enlace al catálogo de productos."""
    return CATALOGO_URL


def obtener_rango_precios() -> dict:
    """Retorna el rango de precios de los productos."""
    return {
        "replicas": {
            "descripcion": "Réplicas Premium 5G Clase A (elite)",
            "precio_minimo": 940,
            "precio_maximo": 1150,
            "moneda": "GTQ",
            "incluye": "Envío gratis, mochila deportiva o calcetines",
        },
        "originales": {
            "descripcion": "Originales clase A, B y C",
            "precio_minimo": 1350,
            "precio_maximo": 3500,
            "moneda": "GTQ",
            "nota": "Estilos y tallas limitadas. Requiere 50% de anticipo.",
        }
    }


def obtener_formas_pago() -> list[str]:
    """Retorna las formas de pago disponibles."""
    return [
        "Contra entrega",
        "VisaCuotas",
        "Depósito bancario",
        "Transferencia bancaria",
    ]


def obtener_info_envio() -> dict:
    """Retorna información sobre el envío."""
    return {
        "empresa": "Cargo Expreso",
        "costo": "GRATIS a todo el país",
        "tiempo_entrega_normal": "Siguiente día hábil (sin horario específico)",
        "tiempo_pedido_especial": "15 a 20 días hábiles",
        "cobertura": "Todo el país",
    }


def validar_datos_pedido(datos: dict) -> dict:
    """
    Valida que un pedido tenga todos los datos necesarios.

    Args:
        datos: Diccionario con los datos del pedido

    Returns:
        {"valido": bool, "faltantes": list[str]}
    """
    campos_requeridos = ["nombre", "direccion", "telefono1", "estilo", "talla"]
    faltantes = [campo for campo in campos_requeridos if not datos.get(campo)]
    return {
        "valido": len(faltantes) == 0,
        "faltantes": faltantes,
    }


# ── Precios de originales en soccer.com ──────────────────────────────────────

COMISION_ORIGINAL_GTQ = 1200  # Comisión fija que se suma al precio convertido


async def obtener_tipo_cambio_usd_gtq() -> float:
    """Obtiene el tipo de cambio actual USD → GTQ desde una API gratuita."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://open.er-api.com/v6/latest/USD")
            if r.status_code == 200:
                data = r.json()
                tasa = data.get("rates", {}).get("GTQ")
                if tasa:
                    return float(tasa)
    except Exception as e:
        logger.warning(f"No se pudo obtener tipo de cambio en línea: {e}")
    # Tipo de cambio aproximado como fallback
    return 7.75


async def buscar_precio_original(modelo: str) -> dict:
    """
    Busca el precio de un modelo original en soccer.com via DuckDuckGo.
    Convierte el precio USD a GTQ y suma Q1,200 de comisión.
    """
    try:
        query = f"{modelo} soccer.com price USD"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True) as client:
            r = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
            )
            html = r.text

        # Extraer URL de soccer.com si aparece en resultados
        urls_soccer = re.findall(r'soccer\.com/[^\s"<>&]+', html)
        url_producto = f"https://www.{urls_soccer[0]}" if urls_soccer else "https://www.soccer.com"

        # Buscar precios: patrones como "$243.04" o "$260.00" en snippets
        precios_raw = re.findall(r'\$\s*(\d{2,4}(?:\.\d{2})?)', html)
        precios_float = sorted(set(float(p) for p in precios_raw if float(p) >= 50))

        if not precios_float:
            return {"encontrado": False, "modelo": modelo, "precio_usd": None,
                    "precio_gtq": None, "url_producto": url_producto, "mensaje": None}

        # Usar el precio más bajo encontrado (generalmente el más representativo)
        precio_usd = precios_float[0]

        # Convertir USD → GTQ y sumar comisión
        tasa = await obtener_tipo_cambio_usd_gtq()
        precio_final = round(precio_usd * tasa) + COMISION_ORIGINAL_GTQ

        mensaje = (
            f"¡Listo Capitán! 😃 Aquí está el precio de los *{modelo}*:\n\n"
            f"💵 Precio en soccer.com: *${precio_usd:.2f} USD*\n"
            f"🇬🇹 Precio final (conversión + importación): *Q{precio_final:,}*\n\n"
            f"✅ Incluye envío GRATIS hasta tu puerta 🚪🚚\n"
            f"💳 Requiere anticipo del *50%* (Q{precio_final // 2:,}) para apartar\n\n"
            f"¿Te interesa ordenarlo, Capi? 🫡"
        )

        return {
            "encontrado": True,
            "modelo": modelo,
            "precio_usd": precio_usd,
            "precio_gtq": precio_final,
            "url_producto": url_producto,
            "mensaje": mensaje,
        }

    except Exception as e:
        logger.error(f"Error buscando precio de '{modelo}': {e}")
        return {"encontrado": False, "modelo": modelo, "precio_usd": None,
                "precio_gtq": None, "url_producto": "https://www.soccer.com", "mensaje": None}


# ── Catálogos de Yupoo ────────────────────────────────────────────────────────
CATALOGOS_YUPOO = [
    {
        "nombre": "dachang88",
        "url_galeria": "https://x.yupoo.com/photos/dachang88/albums?tab=gallery&page={page}",
        "url_base": "https://x.yupoo.com",
        "patron_href": r'href="(/photos/dachang88/albums/\d+[^"]*)',
    },
    {
        "nombre": "wanlian123",
        "url_galeria": "https://wanlian123.x.yupoo.com/albums?tab=gallery&page={page}",
        "url_base": "https://wanlian123.x.yupoo.com",
        "patron_href": r'href="(/albums/\d+[^"]*)',
    },
]

HEADERS_YUPOO = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://x.yupoo.com",
    "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
}


def _normalizar(texto: str) -> str:
    """Normaliza texto para comparación: minúsculas y sin caracteres especiales."""
    return re.sub(r'[^a-z0-9 ]', ' ', texto.lower())


def _calcular_relevancia(titulo_normalizado: str, palabras: list[str]) -> int:
    """Cuenta cuántas palabras de búsqueda aparecen en el título."""
    return sum(1 for p in palabras if p in titulo_normalizado)


async def buscar_fotos_catalogo(modelo: str, max_paginas: int = 4) -> dict:
    """
    Busca álbumes en los catálogos de Yupoo que coincidan con el modelo.

    Args:
        modelo: Nombre del modelo a buscar (ej: "Nike Air Force 1")
        max_paginas: Máximo de páginas a revisar por catálogo

    Returns:
        {
          "encontrado": bool,
          "albums": [{"titulo": str, "url": str, "fotos": int}],
          "imagenes": [str]  # URLs de las primeras imágenes del mejor álbum
        }
    """
    palabras = [p for p in _normalizar(modelo).split() if len(p) > 2]
    if not palabras:
        return {"encontrado": False, "albums": [], "imagenes": []}

    albums_encontrados = []

    async with httpx.AsyncClient(headers=HEADERS_YUPOO, timeout=15, follow_redirects=True) as client:
        for catalogo in CATALOGOS_YUPOO:
            for pagina in range(1, max_paginas + 1):
                try:
                    url = catalogo["url_galeria"].format(page=pagina)
                    r = await client.get(url)
                    if r.status_code != 200:
                        break

                    html = r.text

                    # Extraer pares (href, título) de los álbumes
                    hrefs = re.findall(catalogo["patron_href"], html)
                    titulos = re.findall(r'class="text_overflow album__title">([^<]+)<', html)
                    fotos_counts = re.findall(r'class="text_overflow album__photonumber">(\d+)<', html)

                    for i, href in enumerate(hrefs):
                        titulo = titulos[i].strip() if i < len(titulos) else ""
                        fotos = int(fotos_counts[i]) if i < len(fotos_counts) else 0
                        titulo_norm = _normalizar(titulo)
                        relevancia = _calcular_relevancia(titulo_norm, palabras)

                        if relevancia > 0:
                            url_album = catalogo["url_base"] + href
                            albums_encontrados.append({
                                "titulo": titulo,
                                "url": url_album,
                                "fotos": fotos,
                                "relevancia": relevancia,
                            })

                    # Si no hay más páginas (página vacía), parar
                    if not hrefs:
                        break

                except Exception as e:
                    logger.warning(f"Error buscando en {catalogo['nombre']} página {pagina}: {e}")
                    break

    if not albums_encontrados:
        return {"encontrado": False, "albums": [], "imagenes": []}

    # Ordenar por relevancia (más palabras coinciden = mejor) y cantidad de fotos
    albums_encontrados.sort(key=lambda a: (a["relevancia"], a["fotos"]), reverse=True)
    top_albums = albums_encontrados[:3]

    # Obtener imágenes del mejor álbum
    imagenes = await _obtener_imagenes_album(top_albums[0]["url"])

    # Limpiar campo interno antes de retornar
    for a in top_albums:
        a.pop("relevancia", None)

    return {
        "encontrado": True,
        "albums": top_albums,
        "imagenes": imagenes[:5],  # Máximo 5 imágenes
    }


async def _obtener_imagenes_album(url_album: str) -> list[str]:
    """Extrae las URLs de imágenes (big.png) de un álbum de Yupoo."""
    try:
        async with httpx.AsyncClient(headers=HEADERS_YUPOO, timeout=15, follow_redirects=True) as client:
            r = await client.get(url_album)
            if r.status_code != 200:
                return []
            # Extraer data-src con big.png o big.jpg
            imagenes = re.findall(r'data-src="(https://photo\.yupoo\.com/[^"]+/big\.[a-z]+)"', r.text)
            return list(dict.fromkeys(imagenes))  # Eliminar duplicados manteniendo orden
    except Exception as e:
        logger.warning(f"Error obteniendo imágenes del álbum {url_album}: {e}")
        return []


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."
