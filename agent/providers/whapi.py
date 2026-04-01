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
        self.url_envio = "https://gate.whapi.cloud/messages/text"

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload de Whapi.cloud."""
        body = await request.json()
        mensajes = []
        for msg in body.get("messages", []):
            mensajes.append(MensajeEntrante(
                telefono=msg.get("chat_id", ""),
                texto=msg.get("text", {}).get("body", ""),
                mensaje_id=msg.get("id", ""),
                es_propio=msg.get("from_me", False),
            ))
        return mensajes

    async def reenviar_mensaje(self, mensaje_id: str, telefono_destino: str) -> bool:
        """Reenvía un mensaje existente (texto o imagen) a otro número usando Whapi."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — reenvío no realizado")
            return False
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gate.whapi.cloud/messages/forward",
                json={"message_id": mensaje_id, "to": telefono_destino},
                headers=headers,
            )
            if r.status_code not in (200, 201):
                logger.error(f"Error reenvío Whapi: {r.status_code} — {r.text}")
            return r.status_code in (200, 201)

    async def enviar_imagen(self, telefono: str, url_imagen: str, caption: str = "") -> bool:
        """Envía una imagen desde URL via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — imagen no enviada")
            return False
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {"to": telefono, "media": url_imagen}
        if caption:
            payload["caption"] = caption
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gate.whapi.cloud/messages/image",
                json=payload,
                headers=headers,
            )
            if r.status_code not in (200, 201):
                logger.error(f"Error enviando imagen Whapi: {r.status_code} — {r.text}")
            return r.status_code in (200, 201)

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Whapi.cloud."""
        if not self.token:
            logger.warning("WHAPI_TOKEN no configurado — mensaje no enviado")
            return False
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self.url_envio,
                json={"to": telefono, "body": mensaje},
                headers=headers,
            )
            if r.status_code != 200:
                logger.error(f"Error Whapi: {r.status_code} — {r.text}")
            return r.status_code == 200
