#!/bin/bash
# Publica a app em https://mbmfinancas.duckdns.org atrás do Apache.
# Uso: sudo bash deploy/apply.sh
# Só toca no site mbmfinancas.duckdns.org e no respetivo certificado.
set -e

DOMAIN="mbmfinancas.duckdns.org"
SITE_FILE="/etc/apache2/sites-available/${DOMAIN}.conf"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERRO: corre com sudo: sudo bash deploy/apply.sh" >&2
    exit 1
fi

echo "==> A verificar DNS de ${DOMAIN}..."
PUBLIC_IP="$(curl -s --max-time 10 https://ifconfig.me || true)"
DNS_IP="$(getent ahostsv4 "$DOMAIN" | awk 'NR==1{print $1}' || true)"
if [ -z "$PUBLIC_IP" ]; then
    echo "ERRO: não foi possível obter o IP público (curl https://ifconfig.me falhou)." >&2
    exit 1
fi
if [ "$DNS_IP" != "$PUBLIC_IP" ]; then
    echo "ERRO: ${DOMAIN} resolve para '${DNS_IP:-nada}', mas o IP público desta máquina é ${PUBLIC_IP}." >&2
    echo "      Atualiza o DuckDNS e espera que o DNS propague antes de voltar a correr." >&2
    exit 1
fi
echo "    OK: ${DOMAIN} -> ${DNS_IP}"

echo "==> A instalar ${SITE_FILE}..."
cp "${SCRIPT_DIR}/${DOMAIN}.conf" "$SITE_FILE"
a2ensite "$DOMAIN"

echo "==> A validar a configuração do Apache..."
if ! apache2ctl configtest; then
    echo "ERRO: configtest falhou; a desativar ${DOMAIN} (o Apache em execução não foi alterado)." >&2
    a2dissite "$DOMAIN"
    exit 1
fi

echo "==> A recarregar o Apache..."
systemctl reload apache2

echo "==> A obter o certificado (certbot)..."
certbot --apache -d "$DOMAIN" --redirect

echo "==> Concluído. Teste: curl -I https://${DOMAIN}/api/health"
