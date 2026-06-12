from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://combat:combat@localhost:5432/combat"
    secret_key: str = "change-me-in-production"
    admin_password: str = "combat2026"
    session_code: str = "CHEFS"
    public_url: str = "https://combat-des-chefs.lafrenchsphere.fr"
    cors_origins: str = "https://combat-des-chefs.lafrenchsphere.fr,http://localhost:4200"
    jwt_expire_hours: int = 24

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
