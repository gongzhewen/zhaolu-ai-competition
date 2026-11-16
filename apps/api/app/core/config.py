import json
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "招录智策"
    app_version: str = "0.2.0"
    environment: str = "development"
    debug: bool = True
    deployment_mode: str = "single"
    instance_id: str = "local-1"

    database_url: str = "postgresql+asyncpg://zhaolu:change_me@localhost:5432/zhaolu"
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    redis_key_prefix: str = "zhaolu"
    school_database_urls: str = "{}"
    database_pool_size: int = 8
    database_max_overflow: int = 4
    database_pool_timeout_seconds: float = 30.0
    database_pool_recycle_seconds: int = 300
    database_null_pool: bool = False

    jwt_secret: SecretStr = SecretStr("replace_with_a_long_random_secret")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:3000"
    storage_root: str = "./storage"

    agent_fast_mode: bool = True
    agent_cache_ttl_seconds: int = 60
    agent_chat_timeout_seconds: float = 45.0
    agent_stream_heartbeat_seconds: float = 5.0
    rag_vector_enabled: bool = True
    rag_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    rag_embedding_cache_dir: str = "./models/embedding"
    rag_vector_weight: float = 0.55
    rag_embedding_timeout_seconds: float = 20.0
    router_ml_enabled: bool = True
    router_ml_model_path: str = "./models/router/router.onnx"
    router_ml_tokenizer_path: str = "./models/router/tokenizer.json"
    router_ml_label_map_path: str = "./models/router/label_map.json"
    router_ml_confidence_threshold: float = 0.5
    agent_min_data_support: float = 0.65
    agent_risk_threshold: float = 0.32
    agent_privacy_min_cohort_size: int = 5
    agent_multi_planning_enabled: bool = False
    agent_llm_planner_timeout_seconds: float = 5.0
    agent_plan_consistency_threshold: float = 1.0
    agent_unsupported_answer_alpha: float = 0.0
    agent_p95_latency_budget_ms: float = 2000.0
    agent_shared_cache_enabled: bool = True
    agent_reflection_compression_threshold: int = 4
    runtime_metrics_window_size: int = 1000
    local_sql_model_enabled: bool = False
    local_sql_model_base_url: str = ""
    local_sql_model_name: str = ""
    local_sql_model_api_key: str = ""
    local_sql_timeout_seconds: float = 15.0
    local_sql_max_rows: int = 200
    local_sql_query_timeout_seconds: float = 10.0

    minimind_enabled: bool = False
    minimind_base_url: str | None = None
    minimind_model: str = "MiniMind-3"
    minimind_timeout_seconds: float = 2.5
    minimind_failure_threshold: int = 3
    minimind_reset_seconds: int = 60
    minimind_stable_version: str = "stable"
    minimind_canary_version: str = "canary"
    minimind_canary_percent: int = 0
    minimind_model_versions: str = "{}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def school_database_url_map(self) -> dict[int, str]:
        try:
            payload = json.loads(self.school_database_urls or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        result: dict[int, str] = {}
        for key, value in payload.items():
            if not isinstance(value, str) or not value.strip():
                continue
            try:
                result[int(key)] = value.strip()
            except (TypeError, ValueError):
                continue
        return result

    def database_url_for_school(self, school_id: int | None) -> str | None:
        mapping = self.school_database_url_map
        if mapping:
            if school_id is None:
                return None
            return mapping.get(int(school_id))
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()







