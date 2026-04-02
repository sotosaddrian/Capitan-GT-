# agent/providers/whapi.py — Adaptador para Whapi.cloud
# Generado por AgentKit

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorWhapi(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Whapi.cloud (REST API simple)."""

    def __init__(self):
        self.token = os.getenv("WHAPI_TOKEN")
        channel_id = os.getenv("WHAPI_CHANNEL_ID", "")
        base = f"https://gate.whapi.cloud/{channel_id}" if channel_id else "https://gate.whapi.cloud"
        self.url_base = base
        self.url_envio = f"{base}/messages/text"
        self.url_imagen = f"{base}/messages/image"
        self.url_forward = f"{base}/messages/forward"

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload de Whapi.cloud con manejo robusto de todos los tipos."""
        try:
            body = await request.json()
        except Exception:
            logger.warning("Webhook recibido con body no-JSON — ignorando")
            return []

        mensajes = []
        for msg in body.get("messages", []):
            try:
                tipo = msg.get("type", "")

                # Solo procesar mensajes de texto — ignorar imágenes, audio, video, etc.
                if tipo != "text":
                    logger.debug(f"Mensaje tipo '{tipo}' ignorado")
                    continue

                texto = ""
                text_field = msg.get("text")
                if isinstance(text_field, dict):
                    texto = text_field.get("body", "")
                elif isinstance(text_field, str):
                    texto = text_field

                mensajes.append(MensajeEntrante(
                    telefono=msg.get("chat_id", ""),
                    texto=texto,
                    mensaje_id=msg.get("id", ""),
                    es_propio=msg.get("from_me", False),
                ))
            except Exception as e:
                logger.warning(f"Error procesando mensaje individual: {e} — {msg}")
                continue

        return mensajes

    async def reenviar_mensaje(self, mensaje_id: str, telefono_destino: str) -> bool:
        """Reenvía un mensaje existente (texto o imagen) a otro número usando Whapi."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — reenvío no realizado")
            return False
        try:
            numero = self._normalizar_telefono(telefono_destino)
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    self.url_forward,
                    json={"message_id": mensaje_id, "to": numero},
                    headers=headers,
                )
                if r.status_code not in (200, 201):
                    logger.error(f"Error reenvío Whapi: {r.status_code} — {r.text}")
                return r.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Excepción en reenviar_mensaje: {type(e).__name__}: {e}")
            return False

    async def enviar_imagen(self, telefono: str, url_imagen: str, caption: str = "") -> bool:
        """Envía una imagen desde URL via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — imagen no enviada")
            return False
        try:
            numero = self._normalizar_telefono(telefono)
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            payload = {"to": numero, "media": url_imagen}
            if caption:
                payload["caption"] = caption
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    self.url_imagen,
                    json=payload,
                    headers=headers,
                )
                if r.status_code not in (200, 201):
                    logger.error(f"Error enviando imagen Whapi: {r.status_code} — {r.text}")
                return r.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Excepción en enviar_imagen a {telefono}: {type(e).__name__}: {e}")
            return False

    def _normalizar_telefono(self, telefono: str) -> str:
        """Whapi recibe chat_id con @s.whatsapp.net pero la API de envío solo necesita el número."""
        return telefono.split("@")[0]

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — mensaje no enviado")
            return False
        try:
            numero = self._normalizar_telefono(telefono)
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    self.url_envio,
                    json={"to": numero, "body": mensaje},
                    headers=headers,
                )
                if r.status_code not in (200, 201):
                    logger.error(f"Error Whapi enviar: {r.status_code} — {r.text}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Excepción en enviar_mensaje a {telefono}: {type(e).__name__}: {e}")
            return False
