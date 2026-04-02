# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit

"""
Lógica de IA del agente. Lee el system prompt de prompts.yaml
y genera respuestas usando la API de Anthropic Claude.
"""

import os
import base64
import yaml
import logging
import httpx
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def generar_respuesta(mensaje: str, historial: list[dict]) -> str:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]

    Returns:
        La respuesta generada por Claude
    """
    # Si el mensaje es muy corto o vacío, usar fallback
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    # Construir mensajes para la API
    mensajes = []
    for msg in historial:
        mensajes.append({
            "role": msg["role"],
            "content": msg["content"]
        })

    # Agregar el mensaje actual
    mensajes.append({
        "role": "user",
        "content": mensaje
    })

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=mensajes
        )

        respuesta = response.content[0].text
        logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
        return respuesta

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()


# Precios por tipo de suela
PRECIOS_SUELA = {
    "TF": "Q940",
    "IC": "Q940",
    "FG": "Q980",
    "AG": "Q980",
    "SG": "Q1,150",
}


async def analizar_imagen_zapato(url_imagen: str, token_whapi: str) -> str:
    """
    Analiza una imagen de zapato enviada por el cliente usando Claude Vision.
    Descarga la imagen de Whapi, identifica el tipo de suela y devuelve
    una respuesta con el precio correspondiente.
    """
    try:
        # Descargar la imagen de Whapi (requiere token de autenticación)
        headers_whapi = {"Authorization": f"Bearer {token_whapi}"}
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(url_imagen, headers=headers_whapi, follow_redirects=True)
            if r.status_code != 200:
                logger.error(f"No se pudo descargar imagen: {r.status_code}")
                return obtener_mensaje_error()
            imagen_bytes = r.content
            media_type = r.headers.get("content-type", "image/jpeg").split(";")[0]

        # Convertir a base64 para enviar a Claude
        imagen_b64 = base64.standard_b64encode(imagen_bytes).decode("utf-8")

        prompt_vision = (
            "Eres un experto en calzado deportivo. Analiza esta imagen de zapato(s) que envió un cliente.\n\n"
            "Tu tarea:\n"
            "1. Identifica qué tipo de suela tiene el zapato. Las opciones son:\n"
            "   - TF (Turf / pasto sintético corto)\n"
            "   - IC (Indoor / cancha dura interior)\n"
            "   - FG (Firm Ground / césped natural)\n"
            "   - AG (Artificial Ground / césped artificial de alto rendimiento)\n"
            "   - SG (Soft Ground / terreno blando, tiene tacos largos intercambiables)\n"
            "   - Desconocido (si no puedes determinarlo con certeza)\n\n"
            "2. Basándote en el tipo de suela, responde al cliente con el precio:\n"
            "   - TF o IC → Q940\n"
            "   - FG o AG → Q980\n"
            "   - SG → Q1,150\n\n"
            "Responde directamente al cliente en español, en tono amigable y vendedor. "
            "Menciona el modelo si lo reconoces, el tipo de suela, el precio, "
            "que incluye envío GRATIS, y pregunta su talla en CM. "
            "Llámalo 'Capitán'. Usa emojis con moderación. "
            "Si no puedes identificar el tipo de suela con certeza, muestra los precios disponibles "
            "y pregunta qué tipo de suela necesita."
        )

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": imagen_b64,
                        },
                    },
                    {"type": "text", "text": prompt_vision},
                ],
            }],
        )

        respuesta = response.content[0].text
        logger.info(f"Imagen analizada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
        return respuesta

    except Exception as e:
        logger.error(f"Error analizando imagen: {e}")
        return obtener_mensaje_error()
