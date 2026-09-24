#!/usr/bin/env bash
# Provisiona uma VPS Ubuntu limpa (Hostinger) com Docker + Docker Compose
# para rodar a Eproc Tracker API. Rode como root, uma única vez.
set -euo pipefail

echo "==> Atualizando pacotes do sistema..."
apt-get update -y
apt-get upgrade -y

echo "==> Instalando dependências básicas..."
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg ufw git

echo "==> Instalando Docker Engine + Compose plugin..."
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

echo "==> Configurando firewall (ufw)..."
ufw allow OpenSSH
ufw allow 8000/tcp
ufw --force enable

echo "==> Pronto. Docker:"
docker --version
docker compose version

echo ""
echo "Próximos passos:"
echo "1. Clone o repositório nesta VPS."
echo "2. Copie .env.example para .env e ajuste as senhas."
echo "3. Rode: docker compose up -d --build"
