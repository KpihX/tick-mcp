"""
Saved query preset storage for TickTick MCP.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


class QueryPresetStore:
    """Persist reusable query presets as a local JSON file."""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._path = base_dir / "query_presets.json"

    @property
    def path(self) -> Path:
        return self._path

    def list_presets(self) -> dict[str, Any]:
        data = self._read()
        presets = []
        for name, preset in sorted(data.items()):
            row = dict(preset)
            row["name"] = name
            presets.append(row)
        return {"count": len(presets), "items": presets}

    def save_preset(
        self,
        name: str,
        query_type: str,
        filters: dict[str, Any],
        description: str | None = None,
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("Preset name cannot be empty.")
        allowed = {"tasks", "notes", "agenda", "history", "week_overview", "priority_dashboard"}
        if query_type not in allowed:
            raise ValueError(f"Unsupported query_type '{query_type}'. Allowed: {sorted(allowed)}")

        data = self._read()
        now = datetime.now().astimezone().isoformat()
        existing = data.get(name, {})
        data[name] = {
            "query_type": query_type,
            "filters": filters,
            "description": description,
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        self._write(data)
        return {"saved": True, "name": name, "preset": {"name": name, **data[name]}}

    def get_preset(self, name: str) -> dict[str, Any]:
        data = self._read()
        preset = data.get(name)
        if preset is None:
            raise ValueError(f"Unknown preset '{name}'.")
        return {"name": name, **preset}

    def delete_preset(self, name: str) -> dict[str, Any]:
        data = self._read()
        preset = data.pop(name, None)
        if preset is None:
            raise ValueError(f"Unknown preset '{name}'.")
        self._write(data)
        return {"deleted": True, "name": name}

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
