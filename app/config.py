from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    FERNET_KEY: str
    SCHEMA_NAME: str = "invest"
    TEST_DATABASE_URL: str | None = None
    # 로그인 인증(단일 계정). AUTH_PASSWORD가 비어 있으면 인증 비활성(개발).
    # 값이 설정되면 모든 /api 데이터 접근에 로그인이 강제된다.
    AUTH_USERNAME: str = "admin"
    AUTH_PASSWORD: str = ""
    # 세션 쿠키 서명 키. 비어 있으면 FERNET_KEY에서 파생한다.
    SESSION_SECRET: str = ""
    # https 배포 시 True(Secure 쿠키). http(Tailscale) 배포면 False.
    SESSION_HTTPS_ONLY: bool = False


settings = Settings()
