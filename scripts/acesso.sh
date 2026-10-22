#!/usr/bin/env bash
# Mostra o endereço e o login do aplicativo no terminal do Codespaces.
cd "$(dirname "$0")/.."
echo
echo "================ Rede neural da Ejota ================"
if [ -n "${CODESPACE_NAME:-}" ]; then
  echo "Endereço: https://${CODESPACE_NAME}-8000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
else
  echo "Endereço: http://localhost:8000"
fi
echo "Usuário:  diretor"
if [ -f .senha-local ]; then echo "Senha:    $(cat .senha-local)"; fi
echo "======================================================"
echo
