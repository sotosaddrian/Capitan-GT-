# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp para Capitan GT.
Funciona con cualquier proveedor (Whapi, Meta, Twilio) gracias a la capa de providers.

Flujo de pago:
  1. Cliente confirma forma de pago → David detecta [PAGO_LISTO]
  2. David le dice al cliente "En un momento te enviamos la forma de pago"
  3. El agente notifica al dueño con el número del cliente
  4. El dueño responde al agente (en su chat de WhatsApp) con el link o imagen
  5. El agente reenvía ese mensaje directamente al cliente
"""

import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.tools import buscar_fotos_catalogo, buscar_precio_original
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial,
    agregar_pago_pendiente, obtener_siguiente_pago_pendiente, eliminar_pago_pendiente
)
from agent.providers import obtener_proveedor

load_dotenv()

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Número del dueño para recibir alertas y enviar detalles de pago
OWNER_PHONE = os.getenv("OWNER_PHONE", "")

# Marcador interno para pago
MARCADOR_PAGO = "[PAGO_LISTO]"

# Marcador interno para búsqueda de fotos: [BUSCAR_FOTOS:modelo]
PATRON_BUSCAR_FOTOS = re.compile(r'\[BUSCAR_FOTOS:([^\]]+)\]', re.IGNORECASE)

# Marcador interno para búsqueda de precio original: [BUSCAR_PRECIO:modelo]
PATRON_BUSCAR_PRECIO = re.compile(r'\[BUSCAR_PRECIO:([^\]]+)\]', re.IGNORECASE)


def es_mensaje_del_dueno(telefono: str) -> bool:
    """Verifica si un mensaje proviene del número del dueño."""
    return bool(OWNER_PHONE) and OWNER_PHONE in telefono


async def notificar_dueno(telefono_cliente: str, historial: list[dict]):
    """
    Notifica al dueño que un cliente está listo para pagar.
    El dueño responde con el link/imagen y el agente lo reenvía al cliente.
    """
    if not OWNER_PHONE:
        logger.warning("OWNER_PHONE no configurado — notificación de pago no enviada")
        return

    # Buscar el pedido del cliente en el historial
    resumen = ""
    for msg in reversed(historial):
        if msg["role"] == "user" and len(msg["content"]) > 10:
            resumen = msg["content"][:200]
            break

    mensaje_dueno = (
        f"🔔 *CLIENTE LISTO PARA PAGAR*\n\n"
        f"📱 Número del cliente: {telefono_cliente}\n"
        f"💬 Último mensaje: {resumen}\n\n"
        f"Envíame aquí el link de VisaCuotas o la imagen con los datos bancarios "
        f"y yo se lo reenvío al cliente automáticamente 📲"
    )

    exito = await proveedor.enviar_mensaje(OWNER_PHONE, mensaje_dueno)
    if exito:
        # Registrar al cliente en la cola de pagos pendientes
        await agregar_pago_pendiente(telefono_cliente)
        logger.info(f"Dueño notificado — cliente en cola de pago: {telefono_cliente}")
    else:
        logger.error(f"No se pudo notificar al dueño sobre cliente {telefono_cliente}")


async def manejar_busqueda_fotos(telefono: str, modelo: str):
    """
    Busca fotos del modelo en los catálogos de Yupoo y las envía al cliente.
    Envía hasta 5 imágenes individuales + el link del álbum.
    """
    logger.info(f"Buscando fotos de '{modelo}' para {telefono}")
    resultado = await buscar_fotos_catalogo(modelo)

    CATALOGO_GENERAL = "https://drive.google.com/drive/folders/1Kz7Ft62aoiBx_bq8qyBR0660MmSelN-8?usp=sharing"

    if not resultado["encontrado"]:
        await proveedor.enviar_mensaje(
            telefono,
            f"Busqué *{modelo}* pero no encontré ese estilo exacto 😅\n\n"
            f"¿Puedes darme más detalles? Por ejemplo: marca, color o número de modelo.\n\n"
            f"También puedes ver todos los modelos disponibles aquí 👇\n"
            f"🔗 {CATALOGO_GENERAL}"
        )
        return

    mejor_album = resultado["albums"][0]

    # Enviar imágenes individuales si están disponibles
    imagenes_enviadas = 0
    for i, url_img in enumerate(resultado["imagenes"]):
        caption = f"*{mejor_album['titulo']}* — Foto {i + 1}/{len(resultado['imagenes'])}" if i == 0 else ""
        exito = await proveedor.enviar_imagen(telefono, url_img, caption)
        if exito:
            imagenes_enviadas += 1

    if imagenes_enviadas == 0:
        # Si no pudo enviar imágenes, mandar el catálogo general
        await proveedor.enviar_mensaje(
            telefono,
            f"Aquí puedes ver todos los modelos disponibles incluyendo *{modelo}* 👟\n\n"
            f"🔗 {CATALOGO_GENERAL}\n\n"
            f"¿Te gusta algún estilo, Capitán? Dime cuál y te confirmo precio y disponibilidad 🫡✅"
        )
    else:
        await proveedor.enviar_mensaje(
            telefono,
            f"¿Te gusta este estilo, Capitán? ¿Cuál es tu talla? 👟🫡"
        )

    logger.info(f"Fotos enviadas a {telefono}: {imagenes_enviadas} imágenes")


async def manejar_precio_original(telefono: str, modelo: str):
    """
    Busca el precio de un original en soccer.com, convierte USD→GTQ y suma Q1,200.
    Envía el precio final al cliente.
    """
    logger.info(f"Buscando precio de '{modelo}' para {telefono}")
    resultado = await buscar_precio_original(modelo)

    if resultado["encontrado"] and resultado["mensaje"]:
        await proveedor.enviar_mensaje(telefono, resultado["mensaje"])
    else:
        await proveedor.enviar_mensaje(
            telefono,
            f"Capitán, no encontré el precio exacto de *{modelo}* en este momento 😅\n\n"
            f"Te recomiendo buscarlo directamente en 🔗 https://www.soccer.com\n"
            f"Cuando encuentres el modelo y veas el precio en USD, escríbeme y yo te calculo "
            f"el precio final en quetzales con envío incluido 💪🫡"
        )
    logger.info(f"Precio original enviado a {telefono}: {resultado}")


async def manejar_mensaje_dueno(mensaje_id: str, texto: str):
    """
    Cuando el dueño responde con el link/imagen de pago,
    lo reenvía al siguiente cliente en la cola.
    """
    telefono_cliente = await obtener_siguiente_pago_pendiente()

    if not telefono_cliente:
        logger.info("Dueño envió mensaje pero no hay clientes en cola de pago")
        return

    # Reenviar el mensaje del dueño al cliente (funciona para texto e imágenes)
    exito = await proveedor.reenviar_mensaje(mensaje_id, telefono_cliente)

    if exito:
        await eliminar_pago_pendiente(telefono_cliente)
        logger.info(f"Pago reenviado al cliente {telefono_cliente}")
    else:
        # Si el reenvío falla, intentar enviar el texto como fallback
        if texto:
            await proveedor.enviar_mensaje(telefono_cliente, texto)
            await eliminar_pago_pendiente(telefono_cliente)
            logger.info(f"Pago enviado (texto) al cliente {telefono_cliente}")
        else:
            logger.error(f"No se pudo reenviar el pago al cliente {telefono_cliente}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="AgentKit — Capitan GT WhatsApp Agent",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "service": "capitan-gt-agent"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificación GET del webhook (requerido por Meta Cloud API, no-op para otros)."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via el proveedor configurado.

    - Si el mensaje viene del dueño → reenviar al cliente en cola de pago
    - Si viene de un cliente → procesar con David (Claude AI)
    """
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            # Ignorar mensajes propios o vacíos
            if msg.es_propio or not msg.texto:
                continue

            # ── Mensaje del dueño: reenviar link/imagen al cliente ──
            if es_mensaje_del_dueno(msg.telefono):
                logger.info(f"Mensaje del dueño recibido — reenviando pago al cliente")
                await manejar_mensaje_dueno(msg.mensaje_id, msg.texto)
                continue

            # ── Mensaje de cliente: procesar con David ──
            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial)

            # Detectar marcadores internos en la respuesta de David
            pago_listo = MARCADOR_PAGO in respuesta
            match_fotos = PATRON_BUSCAR_FOTOS.search(respuesta)

            # Limpiar todos los marcadores antes de enviar al cliente
            respuesta_limpia = respuesta.replace(MARCADOR_PAGO, "")
            respuesta_limpia = PATRON_BUSCAR_FOTOS.sub("", respuesta_limpia)
            respuesta_limpia = PATRON_BUSCAR_PRECIO.sub("", respuesta_limpia).strip()

            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta_limpia)
            await proveedor.enviar_mensaje(msg.telefono, respuesta_limpia)

            # Ejecutar acciones de los marcadores detectados
            if pago_listo:
                historial_completo = await obtener_historial(msg.telefono)
                await notificar_dueno(msg.telefono, historial_completo)

            if match_fotos:
                modelo_buscado = match_fotos.group(1).strip()
                await manejar_busqueda_fotos(msg.telefono, modelo_buscado)

            match_precio = PATRON_BUSCAR_PRECIO.search(respuesta)
            if match_precio:
                modelo_precio = match_precio.group(1).strip()
                await manejar_precio_original(msg.telefono, modelo_precio)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta_limpia}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
