#!/usr/bin/env bash
# MMDVM Dashboard MQTT - bilingual clean installer
# Intended for NEW installations only. Never alters MMDVMHost or existing Apache vhosts.
set -Eeuo pipefail
umask 077

APP=/opt/mmdvm-dashboard-mqtt
STATE=/var/lib/mmdvm-dashboard
SERVICE_USER=mmdvm-dashboard
WEBROOT=/var/www/html
SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "MMDVM Dashboard MQTT"
echo "1) English (default)"
echo "2) Italiano"
read -r -p "Language / Lingua [1]: " CHOICE
case "${CHOICE:-1}" in
  1) LANGUAGE=en ;;
  2) LANGUAGE=it ;;
  *) echo "Invalid choice / Scelta non valida"; exit 1 ;;
esac
msg() { if [[ $LANGUAGE == it ]]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
ask() {
  local prompt=$1
  [[ $LANGUAGE == it ]] && prompt=$2
  read -r -p "$prompt" ANSWER
}
die() { msg "$1" "$2" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Run as root." "Eseguire come root."
[[ -f /etc/debian_version ]] || die "Debian/Raspberry Pi OS required." "Richiesto Debian/Raspberry Pi OS."
command -v systemctl >/dev/null && command -v apt-get >/dev/null || die "systemd and apt are required." "Sono richiesti systemd e apt."
for file in backend/app.py backend/mqtt_collector.py backend/telegram_bot.py backend/telegram_settings.py backend/admin_api.py config/dashboard.ini.example frontend/index.html scripts/setup-https.sh; do
  [[ -f "$SRC/$file" ]] || die "Missing source: $file" "File sorgente mancante: $file"
done
[[ ! -e $APP ]] || die "Existing installation found. Aborting." "Installazione esistente. Operazione annullata."
for unit in mmdvm-dashboard-mqtt mmdvm-mqtt-collector mmdvm-telegram-bot; do
  [[ ! -e /etc/systemd/system/$unit.service ]] || die "Existing service: $unit" "Servizio esistente: $unit"
done
for conf in /etc/apache2/conf-available/mmdvm-dashboard-mqtt-api.conf; do
  [[ ! -e $conf && ! -L $conf ]] || die "Existing Apache config: $conf" "Configurazione Apache esistente: $conf"
done
if command -v apache2ctl >/dev/null; then
  msg "Apache is already installed; existing websites will be preserved." "Apache è già installato; i siti esistenti saranno preservati."
else
  msg "Apache will be installed." "Apache verrà installato."
fi

CALLSIGN=
ask "MQTT broker [127.0.0.1]: " "Broker MQTT [127.0.0.1]: "; HOST=${ANSWER:-127.0.0.1}
ask "MQTT port [1883]: " "Porta MQTT [1883]: "; MQTT_PORT=${ANSWER:-1883}
ask "MQTT topic [mmdvm/+/json]: " "Topic MQTT [mmdvm/+/json]: "; TOPIC=${ANSWER:-mmdvm/+/json}
# HTTPS_INSTALL_INTEGRATION_V1
ask "HTTPS IP address or hostname: " "Indirizzo IP o nome host HTTPS: "
HTTPS_NAME=$ANSWER
[[ -n "$HTTPS_NAME" && "$HTTPS_NAME" =~ ^[A-Za-z0-9._:-]+$ ]] ||
  die "Invalid HTTPS address." "Indirizzo HTTPS non valido."

# DEPLOYMENT_MODE_INSTALLER_V2
msg "1) Local  2) Remote MQTT Agent" "1) Locale  2) Agent MQTT remoto"
ask "Connection mode [1]: " "Modalità collegamento [1]: "
case "${ANSWER:-1}" in
  1) DEPLOYMENT_MODE=local ;;
  2) DEPLOYMENT_MODE=remote ;;
  *) die "Invalid mode." "Modalità non valida." ;;
esac

MMDVM_INI=/etc/MMDVM.ini
NODE_ID=
AGENT_PREFIX=

if [[ $DEPLOYMENT_MODE == local ]]; then
  ask "MMDVM.ini path [/etc/MMDVM.ini]: " "Percorso MMDVM.ini [/etc/MMDVM.ini]: "
  MMDVM_INI=${ANSWER:-/etc/MMDVM.ini}
else
  ask "Agent node ID: " "Identificativo nodo Agent: "
  NODE_ID=$ANSWER
  [[ $NODE_ID =~ ^[A-Za-z0-9_.-]+$ ]] || die "Invalid node ID." "Identificativo nodo non valido."
  ask "Agent topic prefix [mmdvm/$NODE_ID]: " "Prefisso topic Agent [mmdvm/$NODE_ID]: "
  AGENT_PREFIX=${ANSWER:-mmdvm/$NODE_ID}
  [[ $AGENT_PREFIX =~ ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$ ]] || die "Invalid Agent prefix." "Prefisso Agent non valido."
fi

[[ $MQTT_PORT =~ ^[0-9]+$ ]] && ((10#$MQTT_PORT>=1 && 10#$MQTT_PORT<=65535)) || die "Invalid MQTT port." "Porta MQTT non valida."
[[ $HOST =~ ^[A-Za-z0-9._:-]+$ ]] || die "Invalid MQTT host." "Host MQTT non valido."
[[ -n $TOPIC && $TOPIC != *$'\n'* && $TOPIC != *$'\r'* ]] || die "Invalid MQTT topic." "Topic MQTT non valido."
[[ $CALLSIGN =~ ^[A-Za-z0-9-]+$ ]] || die "Invalid callsign." "Nominativo non valido."
[[ $MMDVM_INI = /* && $MMDVM_INI != *$'\n'* ]] || die "Invalid MMDVM.ini path." "Percorso MMDVM.ini non valido."
# MMDVM_INI_LOCAL_CHECK_V1
if [[ $DEPLOYMENT_MODE == local ]]; then
  [[ -r $MMDVM_INI ]] || die "MMDVM.ini is not readable." "MMDVM.ini non leggibile."
fi

# The active Apache site keeps its own DocumentRoot and HTTPS configuration.
# Add ONLY /api/ proxy rules, without creating another listener or vhost.
if command -v ss >/dev/null; then
  [[ -z $(ss -H -ltn "sport = :8089") ]] || die "Backend port 8089 is in use." "Porta backend 8089 occupata."
fi
if [[ -d /etc/apache2 ]]; then
  if grep -RIEq '^[[:space:]]*(ProxyPass|Alias|Redirect|<Location)[[:space:]]+["'\''"]?/api(/|["'\''"]|[[:space:]>])' /etc/apache2/sites-enabled /etc/apache2/conf-enabled 2>/dev/null; then
    die "Apache already defines /api/. Review its configuration manually." "Apache gestisce già /api/. Controlla manualmente la configurazione."
  fi
fi

# Refuse all existing web asset collisions unless explicitly approved.
declare -a COLLISIONS=()
while IFS= read -r -d '' file; do
  relative=${file#"$SRC/frontend/"}
  if [[ -e "$WEBROOT/$relative" || -L "$WEBROOT/$relative" ]]; then COLLISIONS+=("$relative"); fi
done < <(find "$SRC/frontend" -type f -print0)
if (( ${#COLLISIONS[@]} )); then
  msg "The following web files already exist:" "I seguenti file web esistono già:"
  printf '  %s\n' "${COLLISIONS[@]}"
  msg "All conflicting files will be backed up before replacement." "Tutti i file in conflitto saranno salvati prima della sostituzione."
  ask "Back up and overwrite these files? [y/N]: " "Creare backup e sovrascrivere questi file? [s/N]: "
  if [[ $LANGUAGE == it ]]; then
    [[ ${ANSWER:-} == [sS] ]] || die "Cancelled." "Annullato."
  else
    [[ ${ANSWER:-} == [yY] ]] || die "Cancelled." "Annullato."
  fi
fi
msg "Existing Apache sites and DocumentRoot directives will NOT be modified." "I siti Apache e le DocumentRoot esistenti NON saranno modificati."
msg "Frontend index.html -> /var/www/html/index.html. Existing Apache VirtualHosts and ports are preserved." "Frontend index.html -> /var/www/html/index.html. VirtualHost e porte Apache esistenti saranno preservati."
msg "The /api/ reverse proxy will be enabled at Apache server level (all VirtualHosts)." "Il proxy /api/ verrà abilitato a livello globale Apache (tutti i VirtualHost)."
msg "HTTPS will be configured automatically if needed." "HTTPS verrà configurato automaticamente se necessario."
ask "Proceed with installation? [y/N]: " "Procedere con l'installazione? [s/N]: "
if [[ $LANGUAGE == it ]]; then
  [[ ${ANSWER:-} == [sS] ]] || exit 0
else
  [[ ${ANSWER:-} == [yY] ]] || exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl ca-certificates apache2 openssl python3 python3-flask python3-werkzeug python3-psutil python3-paho-mqtt

id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -o root -g "$SERVICE_USER" -m 2770 "$APP/config"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$APP/data" "$STATE"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$APP/data/databases"
for dir in backend frontend admin; do cp -a "$SRC/$dir" "$APP/"; done
chown -R root:root "$APP/backend" "$APP/frontend" "$APP/admin"
find "$APP/backend" "$APP/frontend" "$APP/admin" -type d -exec chmod 0755 {} +
find "$APP/backend" "$APP/frontend" "$APP/admin" -type f -exec chmod 0644 {} +
install -o root -g "$SERVICE_USER" -m 0660 "$SRC/config/dashboard.ini.example" "$APP/config/dashboard.ini"

APP="$APP" CALLSIGN="$CALLSIGN" HOST="$HOST" MQTT_PORT="$MQTT_PORT" TOPIC="$TOPIC" MMDVM_INI="$MMDVM_INI" DEPLOYMENT_MODE="$DEPLOYMENT_MODE" NODE_ID="$NODE_ID" AGENT_PREFIX="$AGENT_PREFIX" python3 - <<'PYSET'
import os, json, configparser
from pathlib import Path
root = Path(os.environ['APP'])
p = root/'config/dashboard.ini'
c = configparser.ConfigParser(interpolation=None)
c.read(p)
c.set('repeater', 'callsign', os.environ['CALLSIGN'])
if not c.has_section('deployment'):
    c.add_section('deployment')
c.set('deployment', 'mode', os.environ['DEPLOYMENT_MODE'])
c.set('deployment', 'mmdvm_ini', os.environ['MMDVM_INI'])
c.set('deployment', 'node_id', os.environ['NODE_ID'])
c.set('deployment', 'agent_topic_prefix', os.environ['AGENT_PREFIX'])
m = Path(os.environ['MMDVM_INI'])
if not c.has_section('paths'): c.add_section('paths')
c.set('paths', 'mmdvm_dir', str(m.parent))
c.set('paths', 'mmdvm_file', m.name)
c.set('paths', 'dmr_ids', str(root/'data/databases/DMRIds.dat'))
c.set('paths', 'tg_list_dir', str(root/'data/databases'))
c.set('paths', 'tg_list_file', 'TG_List.csv')
with p.open('w') as f: c.write(f)
q = root/'data/mqtt-settings.json'
q.write_text(json.dumps(dict(host=os.environ['HOST'], port=int(os.environ['MQTT_PORT']), topic=os.environ['TOPIC'], username='', password='', tls=False), indent=2)+'\n')
q.chmod(0o600)
PYSET
chown root:"$SERVICE_USER" "$APP/config/dashboard.ini"
chmod 0660 "$APP/config/dashboard.ini"
chown "$SERVICE_USER:$SERVICE_USER" "$APP/data/mqtt-settings.json"

# Local databases are managed on the DASHBOARD host in both deployment modes.
DB_DIR="$APP/data/databases"
TG_CSV="$DB_DIR/TG_List.csv"
DMR_IDS="$DB_DIR/DMRIds.dat"
if [[ ! -e "$TG_CSV" ]]; then
  printf 'MODE,TS,TG,LABEL,URL\nDMR,1,222,BM-IT,\n' > "$TG_CSV"
  chown "$SERVICE_USER:$SERVICE_USER" "$TG_CSV"
  chmod 0640 "$TG_CSV"
  msg "TG_List.csv created." "TG_List.csv creato."
fi

# DMRIds.dat format: numeric ID, callsign, optional name (whitespace-separated).
# Download into a temporary file, validate it, and publish atomically.
# Source is an independent community mirror; never overwrite existing database.
if [[ ! -s "$DMR_IDS" ]]; then
  DMR_URL=https://raw.githubusercontent.com/DMR-Database/database-beta/master/DMRIds.dat
  DMR_TMP=$(mktemp "$DB_DIR/.dmrids.XXXXXXXX")
  if curl --fail --location --silent --show-error --retry 2 --connect-timeout 15 --max-time 180 \
       --output "$DMR_TMP" "$DMR_URL" && \
     awk 'BEGIN{n=0} $1 ~ /^[0-9]+$/ && NF>=2 {n++} END{exit(n>=100 ? 0 : 1)}' "$DMR_TMP"; then
    chmod 0640 "$DMR_TMP"
    chown "$SERVICE_USER:$SERVICE_USER" "$DMR_TMP"
    mv -f -- "$DMR_TMP" "$DMR_IDS"
    msg "DMR ID database downloaded." "Database ID DMR scaricato."
  else
    rm -f -- "$DMR_TMP"
    msg "WARNING: DMR ID download failed; dashboard installation continues without IDs." \
        "ATTENZIONE: download ID DMR non riuscito; installazione dashboard prosegue senza ID." >&2
  fi
else
  msg "Existing DMR ID database preserved." "Database ID DMR esistente conservato."
fi


# Private Telegram settings are intentionally not copied from any running installation.
# The admin UI creates them when configured.
if [[ ! -f "$STATE/session-secret" ]]; then openssl rand -hex 32 > "$STATE/session-secret"; fi
if [[ ! -f "$STATE/admin.json" && ! -f "$STATE/setup-token" ]]; then openssl rand -hex 24 > "$STATE/setup-token"; fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$STATE"
chmod 0750 "$STATE"
chmod 0600 "$STATE"/*

# Back up every collision, and copy only source files; never delete other websites.
STAMP=$(date +%Y%m%d-%H%M%S)
while IFS= read -r -d '' file; do
  relative=${file#"$SRC/frontend/"}
  target="$WEBROOT/$relative"
  install -d -m 0755 "$(dirname "$target")"
  if [[ -e $target || -L $target ]]; then
    cp -a -- "$target" "$target.bak-mmdvm-$STAMP"
  fi
  cp -- "$file" "$target"
  chmod 0644 "$target"
done < <(find "$SRC/frontend" -type f -print0)

cat > /etc/systemd/system/mmdvm-mqtt-collector.service <<EOF
[Unit]
Description=MMDVM Dashboard MQTT Collector
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP/backend
ExecStart=/usr/bin/python3 -u $APP/backend/mqtt_collector.py
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP/data
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/mmdvm-dashboard-mqtt.service <<EOF
[Unit]
Description=MMDVM Dashboard MQTT Backend
Wants=network-online.target mmdvm-mqtt-collector.service
After=network-online.target
[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP/backend
Environment=MMDVM_DASHBOARD_PORT=8089
Environment=MMDVM_DASHBOARD_STATE_DIR=$STATE
ExecStart=/usr/bin/python3 -u $APP/backend/app.py
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$APP/data $APP/config $STATE
[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/mmdvm-telegram-bot.service <<EOF
[Unit]
Description=MMDVM MQTT Telegram Bot
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$APP/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/default/mmdvm-telegram-bot
ExecStart=/usr/bin/python3 $APP/backend/telegram_bot.py
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
[Install]
WantedBy=multi-user.target
EOF

# API proxy only. Apache continues to serve /var/www/html/index.html itself.
# Existing HTTPS, ports, virtual hosts and DocumentRoot directives are unchanged.
# HTTPS_TRANSACTION_V3: register cleanup BEFORE changing Apache configuration.
HTTPS_CREATED=0
HTTPS_COMMITTED=0
HTTPS_RESULT_FILE=$(mktemp)
chmod 0600 "$HTTPS_RESULT_FILE"
https_install_cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  rm -f -- "${HTTPS_RESULT_FILE:-}"
  if (( rc != 0 && HTTPS_COMMITTED == 0 )); then
    if (( HTTPS_CREATED == 1 )); then
      a2dissite mmdvm-dashboard-mqtt-ssl >/dev/null 2>&1 || true
      rm -f -- /etc/apache2/sites-available/mmdvm-dashboard-mqtt-ssl.conf
      rm -f -- /etc/apache2/ssl/mmdvm-dashboard-mqtt/server.key /etc/apache2/ssl/mmdvm-dashboard-mqtt/server.crt
      rmdir -- /etc/apache2/ssl/mmdvm-dashboard-mqtt 2>/dev/null || true
    fi
    a2disconf mmdvm-dashboard-mqtt-api >/dev/null 2>&1 || true
    rm -f -- /etc/apache2/conf-available/mmdvm-dashboard-mqtt-api.conf
    if apache2ctl configtest >/dev/null 2>&1 && systemctl is-active --quiet apache2; then
      systemctl reload apache2 || true
    fi
    msg "Apache changes rolled back; other installation files may remain." \
        "Modifiche Apache annullate; altri file di installazione potrebbero rimanere." >&2
  fi
  exit "$rc"
}
trap https_install_cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cat > /etc/apache2/conf-available/mmdvm-dashboard-mqtt-api.conf <<EOF
ProxyPass /api/ http://127.0.0.1:8089/api/
ProxyPassReverse /api/ http://127.0.0.1:8089/api/
EOF
a2enmod proxy proxy_http ssl >/dev/null
a2enconf mmdvm-dashboard-mqtt-api >/dev/null

if ! LANGUAGE="$LANGUAGE" HTTPS_RESULT_FILE="$HTTPS_RESULT_FILE" \
    bash "$SRC/scripts/setup-https.sh" "$HTTPS_NAME" "$WEBROOT"; then
  die "HTTPS preparation failed." "Preparazione HTTPS non riuscita."
fi
HTTPS_RESULT=$(cat "$HTTPS_RESULT_FILE")
case "$HTTPS_RESULT" in
  created)
    HTTPS_CREATED=1
    a2ensite mmdvm-dashboard-mqtt-ssl >/dev/null || \
      die "Cannot enable HTTPS site." "Impossibile abilitare il sito HTTPS."
    ;;
  reused)
    msg "Existing HTTPS site preserved." "Sito HTTPS esistente conservato."
    ;;
  *) die "Invalid HTTPS module result." "Risultato modulo HTTPS non valido." ;;
esac
apache2ctl configtest || die "Apache configuration invalid." "Configurazione Apache non valida."
# Do not restart an existing Apache instance if its reload fails.
if systemctl is-active --quiet apache2; then
  systemctl reload apache2 || die "Apache reload failed; no restart attempted." "Reload Apache fallito; nessun riavvio tentato."
else
  systemctl start apache2 || die "Cannot start Apache." "Impossibile avviare Apache."
fi
# Start backend/collector only after Apache configuration is accepted.
systemctl daemon-reload
systemctl enable --now mmdvm-mqtt-collector.service mmdvm-dashboard-mqtt.service
# Do not enable Telegram until configured by the administrator.
systemctl disable mmdvm-telegram-bot.service >/dev/null 2>&1 || true
HTTPS_COMMITTED=1
trap - EXIT INT TERM
rm -f -- "$HTTPS_RESULT_FILE"
msg "Telegram service installed but disabled." "Servizio Telegram installato ma disabilitato."

msg "Installation complete." "Installazione completata."
msg "HTTPS address: https://$HTTPS_NAME/" "Indirizzo HTTPS: https://$HTTPS_NAME/"
msg "Dashboard: /index.html | Administration: /api/admin/" "Dashboard: /index.html | Amministrazione: /api/admin/"
msg "Admin setup token: $STATE/setup-token" "Token configurazione Admin: $STATE/setup-token"
msg "Active services: mmdvm-dashboard-mqtt, mmdvm-mqtt-collector" "Servizi attivi: mmdvm-dashboard-mqtt, mmdvm-mqtt-collector"
msg "Telegram: manual activation after configuration." "Telegram: attivazione manuale dopo la configurazione."
