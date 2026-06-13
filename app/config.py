from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    FERNET_KEY: str
    SCHEMA_NAME: str = "invest"
    TEST_DATABASE_URL: str | None = None


settings = Settings()
