"""HTTP boundary for an independently deployed ArcReel workspace.

No ArcReel source code is embedded here.  The adapter talks to ArcReel's
documented REST surface so its AGPL application remains a separate service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


class ArcReelError(RuntimeError):
    """Raised when the ArcReel sidecar cannot fulfill a request."""


def _base_url(value: str) -> str:
    raw = value.strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ArcReelError("ArcReel base URL must be an http(s) origin without query or fragment")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


@dataclass(frozen=True)
class ArcReelWorkspace:
    base_url: str
    api_key: str | None = None
    timeout_seconds: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _base_url(self.base_url))
        if self.timeout_seconds <= 0 or self.timeout_seconds > 60:
            raise ArcReelError("ArcReel timeout must be between 0 and 60 seconds")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = response.read()
                return json.loads(data.decode("utf-8")) if data else None
        except HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise ArcReelError(f"ArcReel returned HTTP {error.code}: {detail or error.reason}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise ArcReelError(f"ArcReel is unavailable at {self.base_url}: {error}") from error
        except json.JSONDecodeError as error:
            raise ArcReelError("ArcReel returned invalid JSON") from error

    def _request_text(self, method: str, path: str, content: str) -> Any:
        headers = {"Accept": "application/json", "Content-Type": "text/plain; charset=utf-8"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(f"{self.base_url}{path}", data=content.encode("utf-8"), headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                data = response.read()
                return json.loads(data.decode("utf-8")) if data else None
        except HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            raise ArcReelError(f"ArcReel returned HTTP {error.code}: {detail or error.reason}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise ArcReelError(f"ArcReel is unavailable at {self.base_url}: {error}") from error
        except json.JSONDecodeError as error:
            raise ArcReelError("ArcReel returned invalid JSON") from error

    def health(self) -> dict[str, Any]:
        result = self._request("GET", "/health")
        if not isinstance(result, dict):
            raise ArcReelError("ArcReel health response must be an object")
        return result

    def auth_status(self) -> dict[str, Any]:
        result = self._request("GET", "/api/v1/auth/status")
        if not isinstance(result, dict):
            raise ArcReelError("ArcReel auth status must be an object")
        return result

    def list_projects(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/projects")

    def project_names(self) -> list[str]:
        result = self.list_projects()
        items = result.get("projects", []) if isinstance(result, dict) else []
        names: list[str] = []
        for item in items:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and name:
                names.append(name)
        return names

    def get_project(self, project_name: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{quote(project_name, safe='')}")

    def create_project(
        self,
        *,
        name: str,
        title: str,
        style: str,
        generation_mode: str = "storyboard",
        aspect_ratio: str = "9:16",
    ) -> dict[str, Any]:
        return self._request("POST", "/api/v1/projects", {
            "name": name,
            "title": title,
            "style": style,
            "content_mode": "drama",
            "source_kind": "novel",
            "generation_mode": generation_mode,
            "grid_storyboard": False,
            "aspect_ratio": aspect_ratio,
        })

    def ensure_project(self, *, name: str, title: str, style: str, generation_mode: str = "storyboard", aspect_ratio: str = "9:16") -> dict[str, Any]:
        if name in self.project_names():
            return {"status": "exists", "project": self.get_project(name)}
        return {"status": "created", "project": self.create_project(name=name, title=title, style=style, generation_mode=generation_mode, aspect_ratio=aspect_ratio)}

    def workflow_status(self, project_name: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{quote(project_name, safe='')}/workflow-status")

    def put_source_text(self, project_name: str, filename: str, content: str) -> dict[str, Any]:
        if not filename.lower().endswith((".txt", ".md")):
            raise ArcReelError("ArcReel source filename must end in .txt or .md")
        result = self._request_text("PUT", f"/api/v1/projects/{quote(project_name, safe='')}/source/{quote(filename, safe='')}", content)
        if not isinstance(result, dict):
            raise ArcReelError("ArcReel source update response must be an object")
        return result

    def list_tasks(self, project_name: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/projects/{quote(project_name, safe='')}/tasks")

    def submit_storyboard(self, *, project_name: str, segment_id: str, script_file: str, prompt: str | dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/projects/{quote(project_name, safe='')}/generate/storyboard/{quote(segment_id, safe='')}", {"script_file": script_file, "prompt": prompt})

    def submit_video(
        self,
        *,
        project_name: str,
        segment_id: str,
        script_file: str,
        prompt: str | dict[str, Any],
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"script_file": script_file, "prompt": prompt, "narration_delivery": "post_production"}
        if duration_seconds is not None:
            payload["duration_seconds"] = duration_seconds
        return self._request("POST", f"/api/v1/projects/{quote(project_name, safe='')}/generate/video/{quote(segment_id, safe='')}", payload)
