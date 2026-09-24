# Deploy na VPS (Hostinger)

Passo a passo para colocar a Eproc Tracker API rodando na sua VPS via Docker.
Como esta sessão do Claude Code não tem acesso SSH direto à VPS (o ambiente só
permite tráfego HTTPS de saída), os comandos abaixo devem ser colados por você
no terminal da VPS — via SSH do seu computador ou pelo console web do hPanel.

## 0. Antes de tudo: troque a senha de root

Se você chegou a compartilhar a senha de root em algum chat, troque-a agora:

```bash
passwd
```

## 1. Preparar a VPS (uma vez só)

Conecte via SSH como root e rode:

```bash
git clone <URL_DO_SEU_REPOSITORIO> eproc-tracker
cd eproc-tracker
chmod +x deploy/install.sh
./deploy/install.sh
```

Isso instala Docker + Docker Compose e libera a porta 8000 no firewall (ufw).

## 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
nano .env
```

Troque pelo menos `POSTGRES_PASSWORD` (e replique a mesma senha dentro de
`DATABASE_URL`). Não comite o `.env` — ele já está no `.gitignore`.

## 3. Subir os containers

```bash
docker compose up -d --build
```

A primeira build demora alguns minutos (instala o Google Chrome dentro da
imagem). Acompanhe com:

```bash
docker compose logs -f api
```

## 4. Testar

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl -X POST http://localhost:8000/v1/processos \
  -H "Content-Type: application/json" \
  -d '{
    "numero": "1100617-68.2025.8.26.0100",
    "cliente": {"external_id": "cliente_123", "nome": "Cliente Teste"},
    "monitoramento": {"ativo": true, "intervalo_minutos": 60}
  }'

# copie o "id" da resposta acima e use para:
curl -X POST http://localhost:8000/v1/processos/<ID>/consultar
curl http://localhost:8000/v1/processos/<ID>/movimentacoes
```

A documentação interativa (Swagger) fica em `http://<IP_DA_VPS>:8000/docs`.

## 5. Atualizações futuras

```bash
cd eproc-tracker
git pull
docker compose up -d --build
```

## 6. (Opcional) Domínio + HTTPS

Se quiser expor com domínio e certificado em vez de IP:8000, instale Nginx +
Certbot na VPS (fora do Docker) como reverse proxy para `127.0.0.1:8000`, ou
peça para eu preparar um serviço `nginx` adicional no `docker-compose.yml`.

## O que mudou nesta reescrita

- Backend Node.js + Firebase antigo foi removido. A API agora é **Python
  (FastAPI) + PostgreSQL**, rodando em Docker, seguindo o PRD.
- O robô de consulta ao TJSP (e-SAJ, com fallback EPROC) foi portado para
  `app/adapters/tjsp.py`, sem subprocess — roda dentro do próprio processo da
  API, usando Xvfb (display virtual) em vez de `--headless`, porque o e-SAJ
  costuma bloquear o modo headless nativo do Chrome.
- Núcleo implementado agora: cadastro, listagem, detalhe, desativação e
  movimentações de processo, consulta sob demanda com deduplicação por hash
  (processo+data+descrição) e histórico de execuções (`/v1/consultas/{id}`).
- **Ainda não implementado** (próxima fase, conforme combinado): fila
  Redis/Celery para monitoramento periódico automático, webhooks assinados e
  autenticação por API Key. Hoje tudo roda sob um tenant único "default" e a
  consulta só acontece quando você chama `POST /v1/processos/{id}/consultar`.
