# agent/providers/base.py — Clase base para proveedores de WhatsApp
# Generado por AgentKit

"""
Define la interfaz común que todos los proveedores de WhatsApp deben implementar.
Esto permite cambiar de proveedor sin modificar el resto del código.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from fastapi import Request


@dataclass
class MensajeEntrante:
    """Mensaje normalizado — mismo formato sin importar el proveedor."""
    telefono: str           # Número del remitente
    texto: str              # Contenido del mensaje de texto
    mensaje_id: str         # ID único del mensaje
    es_propio: bool         # True si lo envió el agente (se ignora)
    tipo: str = "text"      # "text" o "image"
    url_media: str = ""     # URL de la imagen (solo cuando tipo=="image")


class ProveedorWhatsApp(ABC):
    """Interfaz que cada proveedor de WhatsApp debe implementar."""

    @abstractmethod
    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Extrae y normaliza mensajes del payload del webhook."""
        ...

    @abstractmethod
    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía un mensaje de texto. Retorna True si fue exitoso."""
        ...

    async def reenviar_mensaje(self, mensaje_id: str, telefono_destino: str) -> bool:
        """Reenvía un mensaje existente (por su ID) a otro número. Retorna True si fue exitoso."""
        return False

    async def enviar_imagen(self, telefono: str, url_imagen: str, caption: str = "") -> bool:
        """Envía una imagen desde una URL. Retorna True si fue exitoso."""
        return False

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Verificación GET del webhook (solo Meta la requiere). Retorna respuesta o None."""
        return None
