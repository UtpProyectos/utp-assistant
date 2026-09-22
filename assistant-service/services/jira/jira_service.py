"""Jira Cloud issue creation service."""

from __future__ import annotations

import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import requests


class JiraConfigurationError(RuntimeError):
    """Required Jira connection settings are missing."""


class JiraRequestError(RuntimeError):
    """Jira rejected an API request."""


class JiraService:
    """Create Jira issues using credentials from the Assistant environment."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        project_key: str | None = None,
        epic_issue_type: str | None = None,
        story_issue_type: str | None = None,
        task_issue_type: str | None = None,
        similarity_threshold: float | None = None,
        start_date_field_id: str | None = None,
        todo_status_name: str | None = None,
        timeout: int = 20,
    ) -> None:
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL", "")).rstrip("/")
        self.email = email or os.getenv("JIRA_EMAIL", "")
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN", "")
        self.project_key = project_key or os.getenv("JIRA_PROJECT_KEY", "")
        self.story_issue_type = story_issue_type or os.getenv(
            "JIRA_STORY_ISSUE_TYPE", "Story"
        )
        self.task_issue_type = task_issue_type or os.getenv(
            "JIRA_TASK_ISSUE_TYPE", "Task"
        )
        self.epic_issue_type = epic_issue_type or os.getenv(
            "JIRA_EPIC_ISSUE_TYPE", "Epic"
        )
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else float(os.getenv("JIRA_EPIC_SIMILARITY_THRESHOLD", "0.60"))
        )
        self.start_date_field_id = start_date_field_id or os.getenv(
            "JIRA_START_DATE_FIELD_ID", ""
        )
        self.todo_status_name = (
            todo_status_name
            if todo_status_name is not None
            else os.getenv("JIRA_TODO_STATUS_NAME", "Por hacer")
        )
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        """Return whether all required Jira settings are present."""
        values = (self.base_url, self.email, self.api_token, self.project_key)
        return all(
            value and not (value.startswith("<") and value.endswith(">"))
            for value in values
        )

    def create_issue(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a Story or Task and return its Jira key and URL."""
        required = ("tipo", "titulo", "cliente", "descripcion", "fecha_inicio")
        missing = [field for field in required if not data.get(field)]
        if missing:
            raise ValueError("Campos obligatorios ausentes: " + ", ".join(missing))
        if data["tipo"] not in {"Historia", "Tarea"}:
            raise ValueError("El tipo debe ser Historia o Tarea.")
        if not self.configured:
            raise JiraConfigurationError(
                "Faltan JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN o JIRA_PROJECT_KEY."
            )

        issue_type = (
            self.story_issue_type if data["tipo"] == "Historia" else self.task_issue_type
        )
        issue = self._create_raw_issue(
            summary=data["titulo"],
            issue_type=issue_type,
            description=self._description(data),
            start_date=data["fecha_inicio"],
            due_date=data.get("fecha_vencimiento"),
        )
        return {
            "ticket_key": issue["key"],
            "ticket_url": f"{self.base_url}/browse/{issue['key']}",
        }

    def create_project(self, data: dict[str, Any]) -> dict[str, Any]:
        """Reuse a similar open Epic or create one, then add one Task per requirement."""
        required = ("titulo", "cliente", "descripcion", "fecha_inicio", "requisitos")
        missing = [field for field in required if not data.get(field)]
        if missing:
            raise ValueError("Campos obligatorios ausentes: " + ", ".join(missing))
        if not isinstance(data["requisitos"], list):
            raise ValueError("Los requisitos deben enviarse como una lista.")
        if not self.configured:
            raise JiraConfigurationError(
                "Faltan JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN o JIRA_PROJECT_KEY."
            )

        epic = self._find_similar_epic(data["titulo"])
        epic_reused = epic is not None
        if epic is None:
            epic = self._create_raw_issue(
                summary=data["titulo"],
                issue_type=self.epic_issue_type,
                description=self._description(data),
                start_date=data["fecha_inicio"],
                due_date=data.get("fecha_vencimiento"),
            )

        existing_tasks = self._list_child_tasks(epic["key"])
        created_tasks: list[dict[str, str]] = []
        reused_tasks: list[dict[str, str]] = []
        task_errors: list[dict[str, str]] = []
        for requirement in data["requisitos"]:
            summary = self._task_summary(str(requirement))
            existing = self._find_similar(summary, existing_tasks, threshold=0.90)
            if existing:
                reused_tasks.append(self._issue_result(existing["key"]))
                continue
            try:
                task = self._create_raw_issue(
                    summary=summary,
                    issue_type=self.task_issue_type,
                    description=self._task_description(data, str(requirement)),
                    start_date=data["fecha_inicio"],
                    due_date=data.get("fecha_vencimiento"),
                    parent_key=epic["key"],
                )
                created_tasks.append(self._issue_result(task["key"]))
                existing_tasks.append({"key": task["key"], "summary": summary})
            except (JiraRequestError, KeyError, ValueError) as exc:
                task_errors.append({"requisito": str(requirement), "message": str(exc)})

        return {
            "epic": self._issue_result(epic["key"]),
            "epic_reused": epic_reused,
            "tasks_created": created_tasks,
            "tasks_reused": reused_tasks,
            "task_errors": task_errors,
        }

    def _find_similar_epic(self, title: str) -> dict[str, str] | None:
        jql = (
            f'project = "{self.project_key}" AND issuetype = "{self.epic_issue_type}" '
            "AND resolution IS EMPTY ORDER BY created DESC"
        )
        epics = self._search_issues(jql)
        return self._find_similar(title, epics, self.similarity_threshold)

    def _list_child_tasks(self, epic_key: str) -> list[dict[str, str]]:
        jql = (
            f'parent = "{epic_key}" AND issuetype = "{self.task_issue_type}" '
            "ORDER BY created DESC"
        )
        return self._search_issues(jql)

    def _search_issues(self, jql: str) -> list[dict[str, str]]:
        response = requests.get(
            f"{self.base_url}/rest/api/3/search/jql",
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json"},
            params={"jql": jql, "fields": "summary", "maxResults": 100},
            timeout=self.timeout,
        )
        self._raise_for_jira(response)
        return [
            {"key": issue["key"], "summary": issue.get("fields", {}).get("summary", "")}
            for issue in response.json().get("issues", [])
        ]

    def _create_raw_issue(
        self,
        summary: str,
        issue_type: str,
        description: dict[str, Any],
        start_date: str,
        due_date: str | None = None,
        parent_key: str | None = None,
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "project": {"key": self.project_key},
            "summary": summary[:255],
            "issuetype": {"name": issue_type},
            "description": description,
        }
        if due_date:
            fields["duedate"] = due_date
        fields[self._resolve_start_date_field_id()] = start_date
        if parent_key:
            fields["parent"] = {"key": parent_key}
        response = requests.post(
            f"{self.base_url}/rest/api/3/issue",
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"fields": fields},
            timeout=self.timeout,
        )
        self._raise_for_jira(response)
        issue = response.json()
        self._transition_to_status(issue["key"], self.todo_status_name)
        return issue

    def _resolve_start_date_field_id(self) -> str:
        if self.start_date_field_id:
            return self.start_date_field_id
        response = requests.get(
            f"{self.base_url}/rest/api/3/field",
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        self._raise_for_jira(response)
        for field in response.json():
            if self._normalize(str(field.get("name", ""))) == "fecha de inicio":
                self.start_date_field_id = str(field["id"])
                return self.start_date_field_id
        raise JiraConfigurationError(
            "No se encontró el campo de Jira llamado 'Fecha de inicio'."
        )

    def _transition_to_status(self, issue_key: str, status_name: str) -> None:
        if not status_name:
            return
        response = requests.get(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions",
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        self._raise_for_jira(response)

        target = self._normalize(status_name)
        transition = next(
            (
                item
                for item in response.json().get("transitions", [])
                if self._normalize(str(item.get("to", {}).get("name", ""))) == target
                or self._normalize(str(item.get("name", ""))) == target
            ),
            None,
        )
        if transition is None:
            raise JiraConfigurationError(
                f"No existe una transición disponible hacia '{status_name}' para {issue_key}."
            )
        response = requests.post(
            f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions",
            auth=(self.email, self.api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"transition": {"id": transition["id"]}},
            timeout=self.timeout,
        )
        self._raise_for_jira(response)

    @staticmethod
    def _raise_for_jira(response: requests.Response) -> None:
        if not response.ok:
            raise JiraRequestError(
                f"Jira respondió {response.status_code}: {response.text}"
            )

    def _issue_result(self, key: str) -> dict[str, str]:
        return {"key": key, "url": f"{self.base_url}/browse/{key}"}

    @classmethod
    def _find_similar(
        cls,
        title: str,
        issues: list[dict[str, str]],
        threshold: float,
    ) -> dict[str, str] | None:
        if not issues:
            return None
        best = max(
            issues,
            key=lambda issue: cls._similarity(title, issue.get("summary", "")),
        )
        return (
            best
            if cls._similarity(title, best.get("summary", "")) >= threshold
            else None
        )

    @classmethod
    def _similarity(cls, left: str, right: str) -> float:
        left_normalized, right_normalized = cls._normalize(left), cls._normalize(right)
        if not left_normalized or not right_normalized:
            return 0.0
        left_words = set(left_normalized.split())
        right_words = set(right_normalized.split())
        union = left_words | right_words
        jaccard = len(left_words & right_words) / len(union) if union else 0.0
        sequence = SequenceMatcher(None, left_normalized, right_normalized).ratio()
        return max(jaccard, sequence)

    @staticmethod
    def _normalize(value: str) -> str:
        value = unicodedata.normalize("NFKD", value.lower())
        value = "".join(
            character for character in value if not unicodedata.combining(character)
        )
        return " ".join(re.findall(r"[a-z0-9]+", value))

    @staticmethod
    def _task_summary(requirement: str) -> str:
        cleaned = " ".join(requirement.split())
        return cleaned[:255] or "Requisito sin título"

    @classmethod
    def _task_description(
        cls,
        data: dict[str, Any],
        requirement: str,
    ) -> dict[str, Any]:
        lines = [
            f"Requisito: {requirement}",
            f"Cliente: {data['cliente']}",
            f"Contexto: {data['descripcion']}",
            f"Fecha de inicio (fecha del correo): {data['fecha_inicio']}",
        ]
        if data.get("empresa"):
            lines.insert(2, f"Empresa: {data['empresa']}")
        if data.get("adjuntos"):
            lines.append("Archivos asociados: " + "; ".join(data["adjuntos"]))
        return {
            "type": "doc",
            "version": 1,
            "content": [cls._paragraph(line) for line in lines],
        }

    @staticmethod
    def _paragraph(text: str) -> dict[str, Any]:
        return {"type": "paragraph", "content": [{"type": "text", "text": text}]}

    @classmethod
    def _description(cls, data: dict[str, Any]) -> dict[str, Any]:
        lines = []
        if data.get("cliente"):
            lines.append(f"Cliente: {data['cliente']}")
        if data.get("empresa"):
            lines.append(f"Empresa: {data['empresa']}")
        lines.append(f"Descripción: {data['descripcion']}")
        if data.get("requisitos"):
            lines.append("Requisitos explícitos: " + "; ".join(data["requisitos"]))
        lines.append(f"Fecha de inicio (fecha del correo): {data['fecha_inicio']}")
        if data.get("adjuntos"):
            lines.append("Archivos asociados: " + "; ".join(data["adjuntos"]))
        lines.append(
            f"Fecha de vencimiento explícita: {data['fecha_vencimiento']}"
            if data.get("fecha_vencimiento")
            else "Fecha de vencimiento: pendiente de registro manual."
        )
        if data.get("subtareas"):
            lines.append("Subtareas explícitas: " + "; ".join(data["subtareas"]))
        return {
            "type": "doc",
            "version": 1,
            "content": [cls._paragraph(line) for line in lines],
        }


def crear_ticket_en_jira(datos: dict[str, Any]) -> dict[str, str]:
    """Backward-compatible entry point for callers of the original module."""
    return JiraService().create_issue(datos)
