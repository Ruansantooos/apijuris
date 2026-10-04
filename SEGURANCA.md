# Segurança — lições do pentest

Registro do que o pentest apontou na Eproc Tracker API, o que foi corrigido e o
que fica de checklist para os próximos projetos, para não repetirmos os mesmos
erros.

## 1. O que o pentest encontrou e como foi corrigido

| # | Problema | Risco | Correção | Onde |
|---|----------|-------|----------|------|
| 1 | `DATABASE_URL` tinha valor padrão com usuário e senha no código | Senha versionada no Git; app sobe silenciosamente conectada ao banco errado | Campo obrigatório, sem default: sem a variável a app não inicia | `app/config.py` |
| 2 | Pool de conexões sem limites explícitos | Pico de acessos esgota conexões do Postgres e derruba o banco | `pool_size=20`, `max_overflow=10`, `pool_timeout=30` | `app/database.py` |
| 3 | Conexão com o banco sem exigência de TLS | Dados jurídicos trafegando em texto puro se o banco estiver em outra rede | `DB_REQUIRE_SSL=true` força `sslmode=require` | `app/database.py` |
| 4 | `/docs` e `/openapi.json` públicos em produção | Entrega o mapa completo da API para quem está atacando | Desligados quando `ENVIRONMENT=production` | `app/main.py` |
| 5 | Sem política de CORS | Navegadores sem regra explícita de quais origens podem ler a API | `CORSMiddleware` com origens vindas do `.env` | `app/main.py` |
| 6 | `@app.on_event("startup")` (API depreciada) | Ciclo de vida de recursos sem garantia de fechamento | Trocado por `lifespan` | `app/main.py` |
| 7 | Corrida na criação do tenant padrão | Duas requisições simultâneas com banco vazio → erro 500 | `try/except IntegrityError` + `rollback()` + releitura | `app/deps.py` |
| 8 | Chrome que não morre após falha | Cada consulta com erro deixa centenas de MB presos → VPS sem memória (DoS) | Encerra Chrome, chromedriver e todos os filhos via `psutil` | `app/adapters/tjsp.py` |
| 9 | Navegador reaproveitando cache/cookies | Dados de uma consulta vazando para a próxima | `--incognito`, `--disable-extensions`, `--disable-gpu` | `app/adapters/tjsp.py` |

## 2. Ajustes feitos nas sugestões do pentest

Algumas sugestões estavam certas na intenção, mas precisaram de ajuste para
funcionar de verdade. Vale guardar o porquê:

- **TLS do banco ligado ao `ENVIRONMENT`** — a sugestão exigia SSL sempre que
  `ENVIRONMENT=production`. No nosso `docker-compose`, o Postgres roda na rede
  interna do Docker (o tráfego nem sai da VPS) e a imagem `postgres:16-alpine`
  não vem com SSL habilitado: a API simplesmente não conectaria em produção.
  Virou uma opção própria (`DB_REQUIRE_SSL`), para ligar quando o banco for
  externo/gerenciado. **Lição:** a proteção precisa casar com a topologia real.

- **Limpeza do Chrome com `psutil`** — a sugestão buscava os filhos do Chrome
  *depois* de chamar `driver.quit()`. Testamos: quando o processo pai morre, os
  filhos são adotados pelo `init` e somem de `children()` — justamente os que
  vazavam memória continuavam vivos. Agora a lista é coletada *antes* do
  `quit()`, e o chromedriver também entra. O `kill()` do `psutil` confere a
  hora de criação do processo, então um PID reaproveitado pelo sistema não é
  morto por engano.

- **CORS "protege contra requisições não autorizadas"** — não protege. CORS só
  diz ao *navegador* se ele pode entregar a resposta para um site de outra
  origem. `curl`, scripts e servidores ignoram CORS completamente. Também
  tiramos `localhost` fixo do código (agora vem do `.env`) e
  `allow_credentials` (a API não usa cookie). **Lição:** CORS não é
  autenticação; quem protege a API é a API Key (próxima fase).

- **Esconder `/docs`** — vale como camada extra, mas é *segurança por
  obscuridade*: os endpoints continuam lá. Não substitui autenticação.

- **`env="..."` no `Field`** — no Pydantic v2 esse argumento foi removido e só
  gera aviso. O `pydantic-settings` já liga `database_url` ↔ `DATABASE_URL`
  automaticamente pelo nome.

- **Validação extra do CNJ no `_scrape_eproc`** — não aplicada: o número já
  chega validado (20 dígitos) no `TJSPAdapter`, e só vai para um `send_keys`
  (não é SQL nem comando de shell). Seria código morto.

- **Arquivos enviados com `config.python`, `database.python` etc. na primeira
  linha** — isso é um nome solto e quebraria a app com `NameError` no import.
  Cuidado ao copiar arquivos de relatórios/chats para o código.

## 3. O que encontramos além do pentest (e corrigimos)

| Problema | Risco | Correção |
|----------|-------|----------|
| Container rodando como `root`, com Chrome `--no-sandbox` abrindo sites de terceiros | Uma página que explore o navegador vira root no container | Usuário `app` sem privilégios no `Dockerfile` |
| Sem processo `init` no container | Processos do Chrome encerrados viram zumbis que se acumulam | `init: true` no `docker-compose.yml` |
| Mensagens internas do Selenium devolvidas no campo `error` da API | Vazamento de caminhos, versões e stacktrace | Detalhe só no log; cliente recebe mensagem genérica |
| `?limit=` sem teto | `limit=10000000` faz a API carregar a tabela inteira na memória | `limit` entre 1 e 200 |
| `DEPLOY.md` dizia que o `ufw` protegia a porta 8000 | Falsa sensação de segurança: **Docker ignora o ufw** | Documentação corrigida |

## 4. Ainda em aberto (por prioridade)

1. **API sem autenticação e exposta na internet.** Qualquer pessoa pode
   cadastrar processos e disparar consultas — cada uma abre um Chrome na VPS.
   É o maior risco hoje. Resolver na próxima fase com API Key (guardada como
   hash, conforme o PRD). Até lá: publicar a porta só em `127.0.0.1`.
2. **Sem HTTPS.** Colocar Nginx + Certbot na frente da API (PRD exige HTTPS).
3. **Sem rate limit.** Cada `POST /consultar` segura uma conexão do banco
   enquanto espera o Chrome (até ~100s). 30 consultas paradas esgotam o pool e
   travam todas as outras rotas. A fila (Redis/Celery) da próxima fase resolve
   isso tirando o scraping da requisição HTTP.
4. **Senha de root da VPS foi compartilhada em chat.** Trocar (`passwd`),
   migrar para chave SSH e desativar login de root por senha.
5. **Tabelas criadas com `create_all`.** Migrar para Alembic antes de o schema
   começar a mudar com dados reais em produção.

## 5. Checklist para os próximos projetos

Antes do primeiro deploy, conferir:

**Segredos e configuração**
- [ ] Nenhuma senha, token ou string de conexão com valor padrão no código
- [ ] Configurações obrigatórias sem default: a app falha ao subir se faltarem
- [ ] `.env` no `.gitignore`; só `.env.example` (sem valores reais) versionado
- [ ] Nunca colar senha/token em chat, issue ou commit — se acontecer, trocar

**Rede e infraestrutura**
- [ ] HTTPS obrigatório em produção (Nginx/Caddy + certificado)
- [ ] Banco nunca exposto para fora; TLS se estiver em outra máquina
- [ ] Com Docker, publicar portas em `127.0.0.1` — o ufw não as protege
- [ ] Containers rodando como usuário sem privilégios, nunca `root`
- [ ] `init: true` quando o container cria subprocessos (navegadores, etc.)

**API**
- [ ] Autenticação desde o primeiro endpoint exposto (não "depois")
- [ ] Rate limit por cliente
- [ ] Paginação com teto máximo
- [ ] `/docs` desligado em produção
- [ ] CORS só com as origens necessárias (lembrando: CORS ≠ autenticação)
- [ ] Erros internos só no log; cliente recebe mensagem genérica

**Banco**
- [ ] Pool de conexões com limites e timeout
- [ ] Constraints únicas + tratamento de `IntegrityError` em criações concorrentes
- [ ] Migrações versionadas (Alembic), não `create_all`

**Robôs / navegadores**
- [ ] Concorrência limitada (semáforo / fila)
- [ ] Encerramento garantido do navegador e de todos os filhos, mesmo em erro
- [ ] Sessão isolada por consulta (sem cache/cookies reaproveitados)
- [ ] Operação pesada fora da requisição HTTP (fila + worker)
