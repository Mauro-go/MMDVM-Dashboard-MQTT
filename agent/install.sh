#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

APP=/opt/mmdvm-agent
SERVICE=mmdvm-agent.service
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LANGUAGE=it
SECRET_FILE=''
AGENT_CREATED=false
SERVICE_CREATED=false

say() { if [[ $LANGUAGE == en ]]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
fail() { say "ERRORE: $1" "ERROR: $2" >&2; exit 1; }
cleanup() {
  [[ -z $SECRET_FILE ]] || rm -f -- "$SECRET_FILE"
}
trap cleanup EXIT

ask() {
  local name=$1 it=$2 en=$3 default=$4 answer
  if [[ $LANGUAGE == en ]]; then
    read -r -p "$en [$default]: " answer
  else
    read -r -p "$it [$default]: " answer
  fi
  printf -v "$name" '%s' "${answer:-$default}"
}
ask_secret() {
  local name=$1 it=$2 en=$3 answer
  if [[ $LANGUAGE == en ]]; then
    read -r -s -p "$en: " answer
  else
    read -r -s -p "$it: " answer
  fi
  printf '\n'
  printf -v "$name" '%s' "$answer"
}
confirm() {
  local reply
  if [[ $LANGUAGE == en ]]; then
    read -r -p "$2 [y/N]: " reply
  else
    read -r -p "$1 [s/N]: " reply
  fi
  case "${reply,,}" in s|si|sì|y|yes) return 0 ;; *) return 1 ;; esac
}

[[ $EUID -eq 0 ]] || fail 'eseguire come root.' 'run as root.'
[[ -f $SOURCE_DIR/agent.py ]] || fail 'agent.py non trovato nella directory dello script.' 'agent.py not found beside installer.'
[[ -f $SOURCE_DIR/$SERVICE ]] || fail 'file di servizio systemd mancante.' 'systemd service file missing.'
command -v apt-get >/dev/null || fail 'richiesto Debian/Ubuntu con apt-get.' 'Debian/Ubuntu with apt-get required.'
command -v systemctl >/dev/null || fail 'systemd non disponibile.' 'systemd is not available.'

printf 'Language / Lingua [1=Italiano, 2=English] (1): '
read -r language_choice
case "$language_choice" in 2) LANGUAGE=en ;; ''|1) LANGUAGE=it ;; *) fail 'lingua non valida.' 'invalid language.' ;; esac
say '=== Installazione MMDVM MQTT Agent ===' '=== MMDVM MQTT Agent installation ==='

# All preflight checks precede package changes.
for f in "$APP/agent.py" "$APP/agent.json" "$APP/broker.json" "/etc/systemd/system/$SERVICE"; do
  [[ ! -e $f ]] || fail "file già esistente: $f. Nessuna sovrascrittura." "file already exists: $f. Refusing to overwrite."
done

# L'Agent usa esclusivamente il broker della Dashboard remota.
# Nessuna installazione o modifica di Mosquitto sul ripetitore.

MMDVM_DEFAULT=/etc/MMDVM-Host.ini
if [[ -f "$SOURCE_DIR/detect-mmdvm-config.py" ]]; then
  DETECTED_MMDVM_INI=$(python3 "$SOURCE_DIR/detect-mmdvm-config.py" 2>/dev/null) || true
  if [[ -n $DETECTED_MMDVM_INI ]]; then
    MMDVM_DEFAULT=$DETECTED_MMDVM_INI
  fi
fi

ask MMDVM_INI 'File configurazione MMDVMHost (percorso completo)' 'MMDVMHost configuration file (full path)' "$MMDVM_DEFAULT"
[[ -f $MMDVM_INI && -r $MMDVM_INI ]] || fail 'File MMDVMHost inesistente o illeggibile.' 'MMDVMHost configuration file missing or unreadable.'
DETECTED_NODE=$(awk -F= '
  /^\[General\]/{inside=1;next} /^\[/{inside=0} inside && /^[[:space:]]*Callsign[[:space:]]*=/{gsub(/[[:space:]\r]/,"",$2);print $2;exit}
' "$MMDVM_INI")
DETECTED_NODE=${DETECTED_NODE:-N0CALL}
while :; do
  ask NODE_ID 'Identificativo ponte (node_id)' 'Repeater identifier (node_id)' "$DETECTED_NODE"
  [[ $NODE_ID =~ ^[A-Za-z0-9_-]+$ ]] && break
  say 'node_id non valido, riprovare.' 'Invalid node_id, try again.'
done
say "Prefisso predefinito: mmdvm/<node_id>/agent/v1. Se la Dashboard esiste, inserire il prefisso ESATTO (maiuscole/minuscole contano)." "Default prefix: mmdvm/<node_id>/agent/v1. If Dashboard exists, enter its EXACT prefix (case-sensitive)."
while :; do
  ask TOPIC_PREFIX 'Prefisso topic MQTT' 'MQTT topic prefix' "mmdvm/$NODE_ID/agent/v1"
  TOPIC_PREFIX=${TOPIC_PREFIX#/}; TOPIC_PREFIX=${TOPIC_PREFIX%/}
  [[ $TOPIC_PREFIX =~ ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$ ]] && break
  say 'Prefisso non valido, riprovare.' 'Invalid prefix, try again.'
done
ask INTERVAL 'Intervallo pubblicazione in secondi' 'Publishing interval in seconds' '10'
[[ $INTERVAL =~ ^[0-9]+$ ]] || fail 'intervallo non numerico.' 'interval must be numeric.'
(( 10#$INTERVAL >= 5 )) || fail 'intervallo minimo 5 secondi.' 'minimum interval is 5 seconds.'
INTERVAL=$((10#$INTERVAL))

say 'Connessione al broker della Dashboard remota' 'Connection to remote Dashboard broker'

while :; do
  ask MQTT_HOST 'IP o hostname del broker Dashboard' 'Dashboard broker IP or hostname' ''
  [[ -n $MQTT_HOST ]] && break
  say 'Indirizzo obbligatorio.' 'Broker address is required.'
done

while :; do
  ask MQTT_PORT 'Porta broker MQTT' 'MQTT broker port' '1883'
  if [[ $MQTT_PORT =~ ^[0-9]+$ ]] &&
     (( 10#$MQTT_PORT >= 1 && 10#$MQTT_PORT <= 65535 )); then
    MQTT_PORT=$((10#$MQTT_PORT))
    break
  fi
  say 'Porta non valida.' 'Invalid MQTT port.'
done

if [[ $LANGUAGE == en ]]; then
  read -r -p 'MQTT username (blank if anonymous): ' MQTT_USER
else
  read -r -p 'Username MQTT (vuoto se anonimo): ' MQTT_USER
fi

ask_secret MQTT_PASSWORD 'Password MQTT (non visualizzata)' 'MQTT password (hidden)'

ask TLS_REPLY 'Abilitare TLS? (s/n)' 'Enable TLS? (y/n)' 'n'
case "${TLS_REPLY,,}" in
  s|si|sì|y|yes) MQTT_TLS=true ;;
  n|no) MQTT_TLS=false ;;
  *) fail 'Risposta TLS non valida.' 'Invalid TLS answer.' ;;
esac

say "MMDVM.ini: $MMDVM_INI | Nodo: $NODE_ID | Topic: $TOPIC_PREFIX" "MMDVM.ini: $MMDVM_INI | Node: $NODE_ID | Topic: $TOPIC_PREFIX"
say "Broker Agent: $MQTT_HOST:$MQTT_PORT | TLS: $MQTT_TLS" "Agent broker: $MQTT_HOST:$MQTT_PORT | TLS: $MQTT_TLS"
confirm 'Procedere con installazione?' 'Continue with installation?' || { say 'Annullato.' 'Cancelled.'; exit 0; }

# Store the password outside argv and the exported environment.
SECRET_FILE=$(mktemp)
chmod 600 "$SECRET_FILE"
printf '%s' "$MQTT_PASSWORD" > "$SECRET_FILE"
unset MQTT_PASSWORD

say 'Installazione dipendenze...' 'Installing dependencies...'
apt-get update
packages=(python3 python3-paho-mqtt python3-psutil)
DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"

install -d -o root -g root -m 700 "$APP"
install -o root -g root -m 644 "$SOURCE_DIR/agent.py" "$APP/agent.py"
AGENT_CREATED=true
export APP MMDVM_INI NODE_ID TOPIC_PREFIX INTERVAL MQTT_HOST MQTT_PORT MQTT_USER MQTT_TLS SECRET_FILE
python3 - <<'PY'
import json, os
from pathlib import Path
app = Path(os.environ['APP'])
agent = {
    'node_id': os.environ['NODE_ID'],
    'topic_prefix': os.environ['TOPIC_PREFIX'],
    'interval_seconds': int(os.environ['INTERVAL']),
    'mmdvm_ini': os.environ['MMDVM_INI'],
    'broker_settings_file': str(app / 'broker.json'),
}
broker = {
    'host': os.environ['MQTT_HOST'],
    'port': int(os.environ['MQTT_PORT']),
    'username': os.environ['MQTT_USER'],
    'password': Path(os.environ['SECRET_FILE']).read_text(),
    'tls': os.environ['MQTT_TLS'] == 'true',
}
for name, data in [('agent.json', agent), ('broker.json', broker)]:
    with (app / name).open('x', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    (app / name).chmod(0o600)
PY
rm -f -- "$SECRET_FILE"; SECRET_FILE=''
unset MQTT_USER

say 'Verifica Agent...' 'Checking Agent...'
python3 -B "$APP/agent.py" --config "$APP/agent.json" --dry-run >/dev/null || fail 'verifica Agent fallita, servizio non installato.' 'Agent dry-run failed; service not installed.'
install -o root -g root -m 644 "$SOURCE_DIR/$SERVICE" "/etc/systemd/system/$SERVICE"
SERVICE_CREATED=true
systemctl daemon-reload
systemctl enable --now "$SERVICE"
systemctl is-active --quiet "$SERVICE" || fail 'Agent non attivo; consultare journalctl -u mmdvm-agent.' 'Agent inactive; inspect journalctl -u mmdvm-agent.'
say 'Installazione completata.' 'Installation completed.'
say "Dashboard: usare broker $MQTT_HOST:$MQTT_PORT e prefisso $TOPIC_PREFIX con le stesse credenziali." "Dashboard: use broker $MQTT_HOST:$MQTT_PORT and prefix $TOPIC_PREFIX with matching credentials."
systemctl --no-pager --full status "$SERVICE" || true
