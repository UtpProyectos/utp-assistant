"""CRM Service — llama a la API REST del CRM Flask del grupo."""
from __future__ import annotations

import requests


class CRMService:
    """Cliente HTTP para la API REST del CRM (crm-v2)."""

    def __init__(self, base_url: str = "http://localhost:5000") -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = 10

    # ---------- buscar ----------

    def buscar_por_correo(self, correo: str) -> dict | None:
        """Devuelve el primer cliente que coincida exactamente con ese correo, o None."""
        try:
            r = requests.get(
                f"{self.base_url}/api/clientes",
                params={"correo": correo},
                timeout=self.timeout,
            )
            r.raise_for_status()
            resultados = r.json()
            return resultados[0] if resultados else None
        except Exception as exc:
            raise RuntimeError(f"Error al buscar cliente en CRM: {exc}") from exc

    # ---------- crear / actualizar ----------

    def crear_cliente(self, datos: dict) -> dict:
        """Crea un cliente nuevo. Devuelve el objeto creado con su id."""
        try:
            r = requests.post(
                f"{self.base_url}/api/clientes",
                json=datos,
                timeout=self.timeout,
            )
            r.raise_for_status()
            result = r.json()
            return result
        except Exception as exc:
            raise RuntimeError(f"Error al crear cliente en CRM: {exc}") from exc

    def actualizar_cliente(self, cliente_id: int, datos: dict) -> dict:
        """Actualiza los campos indicados de un cliente existente."""
        try:
            r = requests.put(
                f"{self.base_url}/api/clientes/{cliente_id}",
                json=datos,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            raise RuntimeError(f"Error al actualizar cliente en CRM: {exc}") from exc

    def registrar_accion(self, accion: str, herramienta: str | None = None, detalle: str | None = None) -> None:
        """Registra una accion del asistente en la tabla acciones_chatbot del CRM."""
        try:
            requests.post(
                f"{self.base_url}/api/acciones-chatbot",
                json={"accion": accion, "herramienta": herramienta, "detalle": detalle},
                timeout=self.timeout,
            )
        except Exception:
            pass  # No interrumpir el flujo si el CRM no responde
