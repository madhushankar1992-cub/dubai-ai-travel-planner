"""Validated configuration with deliberately disabled external capabilities."""

import os
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from dubai_planner.system_safety import workspace_write_path


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    data_mode: Literal["local-only"] = "local-only"
    dataset_path: Path = Path("data/curated/dubai-seed.json")
    database_path: Path = Path("runtime/catalog.sqlite")
    llm_provider: str | None = None
    llm_model: str | None = None
    groq_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    gemini_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    ollama_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    ollama_api_key_secondary: SecretStr | None = Field(default=None, exclude=True, repr=False)
    ollama_base_url: Literal["https://ollama.com/api", "http://127.0.0.1:11434/api"] = (
        "https://ollama.com/api"
    )
    groq_model: str = Field(default="llama-3.1-8b-instant", pattern=r"^[a-zA-Z0-9_./-]+$")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", pattern=r"^[a-zA-Z0-9_.-]+$")
    ollama_model: str = Field(default="devstral:24b", pattern=r"^[a-zA-Z0-9_./:-]+$")
    model_routing: Literal["groq-gemini", "ollama-primary", "parallel-ensemble"] = "groq-gemini"
    model_output_tokens: int = Field(default=2048, ge=128, le=8192)
    run_timeout_seconds: int = Field(default=180, gt=0)
    model_timeout_seconds: int = Field(default=45, gt=0)
    provider_timeout_seconds: int = Field(default=10, gt=0)
    max_revisions: int = Field(default=2, ge=0, le=2)
    max_model_calls: int = Field(default=40, gt=0)
    max_model_tokens: int = Field(default=80000, gt=0)
    max_provider_calls: int = Field(default=40, gt=0)

    @model_validator(mode="after")
    def consistent(self):
        if bool(self.llm_provider) != bool(self.llm_model):
            raise ValueError("Set LLM_PROVIDER and LLM_MODEL together, or leave both empty")
        if (
            max(self.model_timeout_seconds, self.provider_timeout_seconds)
            > self.run_timeout_seconds
        ):
            raise ValueError("Request timeouts cannot exceed the run deadline")
        self.database_path = workspace_write_path(self.database_path, purpose="Database")
        return self

    @property
    def capabilities(self) -> dict[str, bool]:
        ollama_available = self.ollama_base_url.startswith("http://127.0.0.1") or bool(
            self.ollama_api_key or self.ollama_api_key_secondary
        )
        if self.model_routing == "ollama-primary":
            model_runner = ollama_available
        elif self.model_routing == "parallel-ensemble":
            model_runner = bool(self.groq_api_key and self.gemini_api_key and ollama_available)
        else:
            model_runner = bool(self.groq_api_key and self.gemini_api_key)
        return {
            "local_data": True,
            "external_travel_data": False,
            "model_runner": model_runner,
        }


def load_settings(
    environ: Mapping[str, str] | None = None, *, env_file: Path | None = None
) -> Settings:
    # Optional file parsing is data-only: no shell execution, expansion or environment writes.
    env = dict(os.environ if environ is None else environ)
    if env_file is not None:
        if env_file.stat().st_size > 16_384:
            raise ValueError("Environment file exceeds size limit")
        for line_number, line in enumerate(
            env_file.read_text(encoding="utf-8-sig").splitlines(), start=1
        ):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if not separator or name.strip().lower() not in Settings.model_fields:
                # Reveal only the line number: a malformed line can itself contain
                # sensitive material, so its text must never be echoed in the UI.
                raise ValueError(
                    f"Environment file contains an unsupported setting on line {line_number}"
                )
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            env.setdefault(name.strip(), value)
    values = {key: env[key.upper()] for key in Settings.model_fields if env.get(key.upper())}
    try:
        return Settings.model_validate(values)
    except ValidationError as exc:
        # Never include input values (which may contain credentials or private paths).
        fields = sorted(
            {
                str(error["loc"][0]) if error["loc"] else "model settings/timeouts"
                for error in exc.errors()
            }
        )
        raise ValueError("Invalid configuration: " + ", ".join(fields)) from None
