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
for file in backend/app.py backend/mqtt_collector.py backend/telegram_bot.py backend/telegram_settings.py backend/admin_api.py config/dashboard.ini.example frontend/index.html; do
  [[ -f "$SRC/$file" ]] || die "Missing source: $file" "File sorgente mancante: $file"
done
[[ ! -e $APP ]] || die "Existing installation found. Aborting." "Installazione esistente. Operazione annullata."
for unit in mmdvm-dashboard-mqtt mmdvm-mqtt-collector mmdvm-telegram-bot; do
  [[ ! -e /etc/systemd/system/$unit.service ]] || die "Existing service: $unit" "Servizio esistente: $unit"
done
for conf in /etc/apache2/conf-available/mmdvm-dashboard-mqtt-api.conf; do
  [[ ! -e $conf ]] || die "Existing Apache config: $conf" "Configurazione Apache esistente: $conf"
done
if command -v apache2ctl >/dev/null; then
  msg "Apache is already installed; existing websites will be preserved." "Apache è già installato; i siti esistenti saranno preservati."
else
  msg "Apache will be installed." "Apache verrà installato."
fi

ask "Repeater callsign [MMDVM]: " "Nominativo ripetitore [MMDVM]: "; CALLSIGN=${ANSWER:-MMDVM}
ask "MQTT broker [127.0.0.1]: " "Broker MQTT [127.0.0.1]: "; HOST=${ANSWER:-127.0.0.1}
ask "MQTT port [1883]: " "Porta MQTT [1883]: "; MQTT_PORT=${ANSWER:-1883}
ask "MQTT topic [mmdvm/+/json]: " "Topic MQTT [mmdvm/+/json]: "; TOPIC=${ANSWER:-mmdvm/+/json}
ask "MMDVM.ini path (read-only) [/etc/MMDVM.ini]: " "Percorso MMDVM.ini (sola lettura) [/etc/MMDVM.ini]: "; MMDVM_INI=${ANSWER:-/etc/MMDVM.ini}

[[ $MQTT_PORT =~ ^[0-9]+$ ]] && ((10#$MQTT_PORT>=1 && 10#$MQTT_PORT<=65535)) || die "Invalid MQTT port." "Porta MQTT non valida."
[[ $HOST =~ ^[A-Za-z0-9._:-]+$ ]] || die "Invalid MQTT host." "Host MQTT non valido."
[[ -n $TOPIC && $TOPIC != *$'\n'* && $TOPIC != *$'\r'* ]] || die "Invalid MQTT topic." "Topic MQTT non valido."
[[ $CALLSIGN =~ ^[A-Za-z0-9-]+$ ]] || die "Invalid callsign." "Nominativo non valido."
[[ $MMDVM_INI = /* && $MMDVM_INI != *$'\n'* ]] || die "Invalid MMDVM.ini path." "Percorso MMDVM.ini non valido."
[[ -r $MMDVM_INI ]] || msg "Warning: MMDVM.ini is not readable." "Attenzione: MMDVM.ini non è leggibile."

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
msg "Admin authentication requires an existing HTTPS site; this installer does not create one." "L'accesso Admin richiede un sito HTTPS esistente; l'installer non ne crea uno."
ask "Proceed with installation? [y/N]: " "Procedere con l'installazione? [s/N]: "
if [[ $LANGUAGE == it ]]; then
  [[ ${ANSWER:-} == [sS] ]] || exit 0
else
  [[ ${ANSWER:-} == [yY] ]] || exit 0
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y apache2 openssl python3 python3-flask python3-werkzeug python3-psutil python3-paho-mqtt

id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home "$APP" --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -o root -g "$SERVICE_USER" -m 2770 "$APP/config"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$APP/data" "$STATE"
for dir in backend frontend admin; do cp -a "$SRC/$dir" "$APP/"; done
chown -R root:root "$APP/backend" "$APP/frontend" "$APP/admin"
find "$APP/backend" "$APP/frontend" "$APP/admin" -type d -exec chmod 0755 {} +
find "$APP/backend" "$APP/frontend" "$APP/admin" -type f -exec chmod 0644 {} +
install -o root -g "$SERVICE_USER" -m 0660 "$SRC/config/dashboard.ini.example" "$APP/config/dashboard.ini"

APP="$APP" CALLSIGN="$CALLSIGN" HOST="$HOST" MQTT_PORT="$MQTT_PORT" TOPIC="$TOPIC" MMDVM_INI="$MMDVM_INI" python3 - <<'PYSET'
import os, json, configparser
from pathlib import Path
root = Path(os.environ['APP'])
p = root/'config/dashboard.ini'
c = configparser.ConfigParser(interpolation=None)
c.read(p)
c.set('repeater', 'callsign', os.environ['CALLSIGN'])
m = Path(os.environ['MMDVM_INI'])
c.set('paths', 'mmdvm_dir', str(m.parent))
c.set('paths', 'mmdvm_file', m.name)
with p.open('w') as f: c.write(f)
q = root/'data/mqtt-settings.json'
q.write_text(json.dumps(dict(host=os.environ['HOST'], port=int(os.environ['MQTT_PORT']), topic=os.environ['TOPIC'], username='', password='', tls=False), indent=2)+'\n')
q.chmod(0o600)
PYSET
chown root:"$SERVICE_USER" "$APP/config/dashboard.ini"
chmod 0660 "$APP/config/dashboard.ini"
chown "$SERVICE_USER:$SERVICE_USER" "$APP/data/mqtt-settings.json"

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
cat > /etc/apache2/conf-available/mmdvm-dashboard-mqtt-api.conf <<EOF
ProxyPass /api/ http://127.0.0.1:8089/api/
ProxyPassReverse /api/ http://127.0.0.1:8089/api/
EOF
a2enmod proxy proxy_http >/dev/null
a2enconf mmdvm-dashboard-mqtt-api >/dev/null
apache2ctl configtest
systemctl daemon-reload
systemctl enable --now mmdvm-mqtt-collector.service mmdvm-dashboard-mqtt.service mmdvm-telegram-bot.service
systemctl reload apache2 || systemctl restart apache2

msg "Installation complete. Open your existing Apache HTTPS website." "Installazione completata. Apri il sito HTTPS Apache già configurato."
msg "Dashboard: /index.html | Administration: /api/admin/" "Dashboard: /index.html | Amministrazione: /api/admin/"
msg "Admin setup token: $STATE/setup-token" "Token configurazione Admin: $STATE/setup-token"
msg "Services: mmdvm-dashboard-mqtt, mmdvm-mqtt-collector, mmdvm-telegram-bot" "Servizi: mmdvm-dashboard-mqtt, mmdvm-mqtt-collector, mmdvm-telegram-bot"
