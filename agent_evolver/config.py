"""Unified configuration via Pydantic Settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class EvolverConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Directories ──
    evolver_production_dir: Path = Path.home() / ".agent" / "skills"
    evolver_candidate_dir: Path = Path.home() / ".agent-evolver" / "candidate"
    evolver_audit_dir: Path = Path.home() / ".agent-evolver" / "audit"

    # ── Upstream LLM ──
    evolver_upstream_base_url: str = "https://api.openai.com/v1"
    evolver_upstream_api_key: str = ""
    evolver_upstream_model: str = "gpt-4o"

    # ── Proxy ──
    evolver_proxy_host: str = "127.0.0.1"
    evolver_proxy_port: int = 30000

    # ── Dashboard ──
    evolver_dashboard_host: str = "127.0.0.1"
    evolver_dashboard_port: int = 30001

    # ── Evolution Engine ──
    evolver_strategy: str = "balanced"
    evolver_confidence_threshold: float = 0.7
    evolver_llm_model: str = "gpt-4o-mini"

    # ── Semantic Pattern Mining ──
    evolver_semantic_min_similarity: float = 0.7
    evolver_semantic_max_sessions: int = 20
    evolver_pattern_min_occurrences: int = 3
    evolver_pattern_confidence_boost_max: float = 0.2

    # ── Security ──
    evolver_strict_readonly: bool = False

    @property
    def proxy_url(self) -> str:
        return f"http://{self.evolver_proxy_host}:{self.evolver_proxy_port}"

    @property
    def dashboard_url(self) -> str:
        return f"http://{self.evolver_dashboard_host}:{self.evolver_dashboard_port}"

    @property
    def storage_db_path(self) -> Path:
        return self.evolver_candidate_dir / ".evolver" / "storage.db"

    @property
    def candidate_db_path(self) -> Path:
        return self.evolver_candidate_dir / ".evolver" / "candidates.db"

    @property
    def audit_events_path(self) -> Path:
        return self.evolver_audit_dir / "events.jsonl"

    def ensure_dirs(self) -> None:
        self.evolver_production_dir.mkdir(parents=True, exist_ok=True)
        self.evolver_candidate_dir.mkdir(parents=True, exist_ok=True)
        self.evolver_audit_dir.mkdir(parents=True, exist_ok=True)
        self.storage_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.candidate_db_path.parent.mkdir(parents=True, exist_ok=True)


# Singleton — imported everywhere
_settings: EvolverConfig | None = None


def get_config() -> EvolverConfig:
    global _settings
    if _settings is None:
        _settings = EvolverConfig()
        _settings.ensure_dirs()
    return _settings


def _reset_config() -> None:
    """Reset the config singleton. Used only in tests."""
    global _settings
    _settings = None
