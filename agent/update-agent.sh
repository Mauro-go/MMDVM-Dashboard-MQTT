#!/bin/bash
set -Eeuo pipefail

APP=/opt/mmdvm-agent
SERVICE=mmdvm-agent.service
UNIT=/etc/systemd/system/$SERVICE
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_ROOT=/var/backups/mmdvm-agent
STAMP="$(date -u +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_ROOT/$STAMP"
STAGING="$(mktemp -d /tmp/mmdvm-agent-update.XXXXXX)"

cleanup() {
    rm -rf "$STAGING"
}
trap cleanup EXIT

fail() {
    echo "ERRORE: $*"
    return 1
}

if [ "$(id -u)" -ne 0 ]; then
    fail "Eseguire come root."
    exit 1
fi

echo "===== VERIFICA PACCHETTO ====="

for f in VERSION agent.py detect-mmdvm-config.py; do
    [ -f "$SOURCE_DIR/$f" ] || {
        fail "File mancante: $f"
        exit 1
    }
done

PACKAGE_VERSION="$(cat "$SOURCE_DIR/VERSION")"

python3 - "$SOURCE_DIR" "$APP" <<'PY'
import ast
import sys
from pathlib import Path

source = Path(sys.argv[1])
app = Path(sys.argv[2])

version = (source / "VERSION").read_text().strip()
tree = ast.parse((source / "agent.py").read_text())

found = None
for node in tree.body:
    if isinstance(node, ast.Assign):
        if any(isinstance(t, ast.Name) and t.id == "VERSION"
               for t in node.targets):
            found = ast.literal_eval(node.value)

if found != version:
    raise SystemExit("Versione del pacchetto non coerente")

if not (app / "agent.json").is_file():
    raise SystemExit("Configurazione agent.json assente")

if not (app / "broker.json").is_file():
    raise SystemExit("Configurazione broker.json assente")

print("Versione pacchetto:", version)
print("Configurazioni esistenti: OK")
PY

[ -f "$APP/agent.py" ] || {
    fail "Agent installato non trovato"
    exit 1
}

[ -f "$UNIT" ] || {
    fail "Servizio systemd non trovato"
    exit 1
}

echo
echo "===== PREPARAZIONE CANDIDATO ====="

install -m 600 "$SOURCE_DIR/agent.py" "$STAGING/agent.py"
install -m 644 "$SOURCE_DIR/detect-mmdvm-config.py" \
    "$STAGING/detect-mmdvm-config.py"

python3 -B "$STAGING/agent.py" \
    --config "$APP/agent.json" --dry-run \
    > "$STAGING/dry-run.json"

python3 -m json.tool "$STAGING/dry-run.json" >/dev/null

echo "OK: Agent candidato funzionante"

echo
echo "===== BACKUP COMPLETO ====="

install -d -m 700 "$BACKUP_ROOT"
install -d -m 700 "$BACKUP"

tar -czf "$BACKUP/installation.tar.gz" \
    -C / opt/mmdvm-agent \
    etc/systemd/system/mmdvm-agent.service

chmod 600 "$BACKUP/installation.tar.gz"

sha256sum "$BACKUP/installation.tar.gz" \
    > "$BACKUP/SHA256SUMS"

echo "Backup creato: $BACKUP"

echo
echo "===== INSTALLAZIONE ====="

systemctl stop "$SERVICE"

install -o root -g root -m 644 \
    "$STAGING/agent.py" "$APP/agent.py"

install -o root -g root -m 644 \
    "$STAGING/detect-mmdvm-config.py" \
    "$APP/detect-mmdvm-config.py"

echo
echo "===== VERIFICA E RIAVVIO ====="

if systemctl restart "$SERVICE" &&
   systemctl is-active --quiet "$SERVICE"; then

    echo "OK: Agent aggiornato"
    echo "Versione: $PACKAGE_VERSION"
    echo "Backup conservato: $BACKUP"

else
    echo "ERRORE: aggiornamento fallito"
    echo "Avvio rollback..."

    systemctl stop "$SERVICE" || true

    tar -xzf "$BACKUP/installation.tar.gz" -C /

    systemctl daemon-reload
    systemctl restart "$SERVICE" || true

    if systemctl is-active --quiet "$SERVICE"; then
        echo "ROLLBACK COMPLETATO"
    else
        echo "ATTENZIONE: verificare manualmente il servizio"
    fi

    exit 1
fi
