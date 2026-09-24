from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    access_token_expire_days: int = 30
    cors_origins: str = "*"
    # Código que quem já tem conta usa para convidar novos utilizadores.
    # Muda isto no .env para algo só teu.
    admin_invite_code: str = "muda-me"

    class Config:
        env_file = ".env"


settings = Settings()
