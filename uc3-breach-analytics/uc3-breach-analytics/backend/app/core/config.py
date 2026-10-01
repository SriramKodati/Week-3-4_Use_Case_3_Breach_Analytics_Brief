"""
Central settings. Two independent tier providers (not one), matching
Design Doc Section 7.3: Tier 1 is the cheap/routine model, Tier 2 is the
escalation model AND what every agent runs on (agents need reasoning
quality, not cost-optimization — see Section 7.3's rejected alternative).
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./uc3.db"

    tier1_provider: str = "local"   # deepseek | local
    tier2_provider: str = "local"   # anthropic | local
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    api_key: str = "dev-local-key"

    tier1_escalation_threshold: float = 0.7
    entity_match_confident_threshold: float = 0.85
    entity_match_ambiguous_floor: float = 0.55
    flag_review_threshold: float = 0.75

    run_token_budget: int = 200_000
    run_spend_budget_usd: float = 5.00

    upload_dir: str = "./uploads"

    class Config:
        env_file = ".env"


settings = Settings()
