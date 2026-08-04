"""
app/config.py
Central settings, loaded from environment variables. No secrets are ever
hardcoded — this is the single source of truth for distributor credentials,
Stripe keys, and default markup behavior.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://hf_user:hf_pass@localhost:5432/hardwarefabric"

    # --- Stripe ---
    stripe_secret_key: str
    stripe_webhook_secret: str

    # --- Ingram Micro API ---
    ingram_micro_base_url: str = "https://api.ingrammicro.com:443/sandbox/resellers/v6"
    ingram_micro_client_id: str
    ingram_micro_client_secret: str
    ingram_micro_customer_number: str
    ingram_micro_sender_id: str = "hardwarefabric"

    # --- Arrow Electronics API ---
    arrow_base_url: str = "https://api.arrow.com/sandbox/v2"
    arrow_api_key: str
    arrow_account_number: str

    # --- Pricing defaults ---
    default_markup_percent: float = 18.0
    default_min_margin_cents: int = 500  # $5.00 floor per line item

    # --- Auth ---
    jwt_secret_key: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # --- CORS ---
    frontend_origin: str = "http://localhost:3000"

    # --- Distributor sync worker / pricing cache ---
    distributor_offer_cache_ttl_minutes: int = 15

    # --- Email (verification links, etc.) ---
    # Plain SMTP so this works against any provider (Namecheap Private Email,
    # Gmail, etc.) without an API-specific integration. If smtp_host is left
    # blank, the app logs the verification link instead of sending mail —
    # lets registration/verification be tested end-to-end before a real
    # mailbox exists.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = "no-reply@hardwarefabric.tech"
    smtp_from_name: str = "HardwareFabric"
    email_verification_token_expire_hours: int = 24
    # Used to build the verification link sent in the email (frontend route,
    # not the API host).
    frontend_verify_email_path: str = "/verify-email"

    # --- HardwareFabric fulfillment identity (used on blind dropship packing) ---
    ship_from_company_name_override: str = "HardwareFabric"
    dropship_return_address_line1: str = "HardwareFabric Returns Processing"
    dropship_return_address_city: str = "Austin"
    dropship_return_address_state: str = "TX"
    dropship_return_address_zip: str = "78701"
    dropship_return_address_country: str = "US"


@lru_cache
def get_settings() -> Settings:
    return Settings()
