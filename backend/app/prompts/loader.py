"""Versioned prompt loader with path confinement and SHA-256 provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


class PromptNotFoundError(KeyError):
    pass


class PromptIntegrityError(RuntimeError):
    pass


class PromptArtifact(BaseModel):
    name: str
    version: str
    filename: str
    content: str
    sha256: str


class PromptLoader:
    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = (base_path or Path(__file__).resolve().parent).resolve()
        manifest_path = self.base_path / "manifest.yaml"
        try:
            # The manifest intentionally uses JSON syntax, which is valid YAML and
            # lets the runtime avoid a YAML parser dependency.
            self._manifest: dict[str, object] = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as exc:
            raise PromptNotFoundError("Prompt manifest is missing") from exc
        except json.JSONDecodeError as exc:
            raise PromptIntegrityError("Prompt manifest is not valid JSON-compatible YAML") from exc

    def load(self, name: str, version: str | None = None) -> PromptArtifact:
        prompts = self._manifest.get("prompts")
        if not isinstance(prompts, dict) or name not in prompts:
            raise PromptNotFoundError(f"Unknown prompt: {name}")
        definition = prompts[name]
        if not isinstance(definition, dict):
            raise PromptIntegrityError(f"Invalid manifest entry for {name}")
        selected_version = version or definition.get("default_version")
        versions = definition.get("versions")
        if (
            not isinstance(selected_version, str)
            or not isinstance(versions, dict)
            or selected_version not in versions
        ):
            raise PromptNotFoundError(f"Unknown prompt version: {name}@{selected_version}")
        entry = versions[selected_version]
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise PromptIntegrityError(f"Invalid prompt version entry: {name}@{selected_version}")
        filename = entry["file"]
        path = (self.base_path / filename).resolve()
        if path.parent != self.base_path:
            raise PromptIntegrityError("Prompt path escapes the prompt directory")
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PromptNotFoundError(f"Prompt file is missing: {filename}") from exc
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        expected = entry.get("sha256")
        if expected and expected != digest:
            raise PromptIntegrityError(f"Prompt hash mismatch: {name}@{selected_version}")
        return PromptArtifact(
            name=name,
            version=selected_version,
            filename=filename,
            content=content,
            sha256=digest,
        )

    def versions(self, name: str) -> tuple[str, ...]:
        prompts = self._manifest.get("prompts", {})
        if not isinstance(prompts, dict) or name not in prompts:
            raise PromptNotFoundError(f"Unknown prompt: {name}")
        definition = prompts[name]
        versions = definition.get("versions", {}) if isinstance(definition, dict) else {}
        return tuple(sorted(versions))


_default_loader: PromptLoader | None = None


def load_prompt(name: str, version: str | None = None) -> PromptArtifact:
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader.load(name, version)


__all__ = [
    "PromptArtifact",
    "PromptIntegrityError",
    "PromptLoader",
    "PromptNotFoundError",
    "load_prompt",
]
