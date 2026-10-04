from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # dev | staging | production. Em production a documentação (/docs) fica oculta.
    environment: str = "dev"

    # Sem valor padrão de propósito: um default com usuário/senha acabaria versionado
    # no Git, e a app poderia subir conectada ao banco errado sem ninguém perceber.
    # Sem DATABASE_URL no ambiente, a app nem inicia (ValidationError: field required).
    database_url: str = Field(..., description="String de conexão com o PostgreSQL")

    # Exige TLS na conexão com o banco. Ligue quando o Postgres estiver em outra
    # máquina/rede (banco gerenciado). No docker-compose o banco fica na rede
    # interna do Docker e a imagem postgres:16-alpine não vem com SSL habilitado.
    db_require_ssl: bool = False

    # Origens de navegador autorizadas a ler respostas da API (CORS).
    # No .env, em JSON: CORS_ORIGINS=["https://painel.seudominio.com.br"]
    cors_origins: list[str] = []

    scraper_timeout_seconds: int = 25
    scraper_max_concurrency: int = 1
    scraper_use_xvfb: bool = True
    chrome_binary: str | None = None

    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
