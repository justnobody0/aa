#!/usr/bin/env bash
# Sobe o aplicativo em segundo plano na porta 8000 (usado pelo Codespaces).
set -euo pipefail
cd "$(dirname "$0")/.."

python -m ejota.cli configurar-local

if curl -sf http://127.0.0.1:8000/saude >/dev/null 2>&1; then
  echo "O aplicativo já está rodando."
  exit 0
fi
setsid nohup python -m uvicorn ejota.main:app --host 0.0.0.0 --port 8000 --workers 1 --no-server-header \
  > servidor.log 2>&1 < /dev/null &
for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8000/saude >/dev/null 2>&1 && { echo "Aplicativo no ar na porta 8000."; exit 0; }
  sleep 1
done
echo "O aplicativo não subiu. Veja servidor.log." >&2
exit 1
