"""Configuración de la aplicación vía variables de entorno (pydantic-settings)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://onevideo:cambiame@db:5432/onevideo"
    secret_key: str = "cambiame-64-chars"
    access_token_expire_minutes: int = 1440
    cors_origins: str = "http://localhost:5173"
    mediamtx_api_url: str = "http://mediamtx:9997"
    # Secreto compartido con MediaMTX para autenticar el hook /internal/mediamtx/auth.
    # Vacío (dev/tests): se exige que la IP del llamante sea privada/loopback.
    mediamtx_auth_secret: str = ""
    stream_public_url: str = "http://localhost:8889"
    usage_tracker_enabled: bool = True
    usage_tracker_interval_seconds: int = 30
    # Correos separados por comas habilitados para el bootstrap del panel de administración.
    superadmin_emails: str = ""
    # Secreto de un solo uso que además hay que enviar en el registro o el inicio de
    # sesión para que el bootstrap promueva la cuenta. Vacío = autoservicio apagado
    # (solo queda el CLI `scripts/manage.py promote`). Sin este secreto, cualquiera
    # que se adelante a registrar un correo de la lista se volvería administrador.
    superadmin_bootstrap_token: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def superadmin_emails_list(self) -> list[str]:
        return [email.strip().lower() for email in self.superadmin_emails.split(",") if email.strip()]


settings = Settings()
