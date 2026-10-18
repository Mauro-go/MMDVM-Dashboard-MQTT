#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
APP=/opt/mmdvm-dashboard-mqtt
STATE=/var/lib/mmdvm-dashboard
SERVICE_USER=mmdvm-dashboard
SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ $EUID -eq 0 ]] || { echo 'Eseguire come root'; exit 1; }
[[ -f "$SRC/backend/app.py" && -f "$SRC/config/dashboard.ini.example" ]] || { echo 'Sorgenti mancanti'; exit 1; }
[[ ! -e "$APP" ]] || { echo "ERRORE: $APP esiste già; nessuna modifica eseguita."; exit 1; }
for unit in /etc/systemd/system/mmdvm-dashboard-mqtt.service /etc/systemd/system/mmdvm-mqtt-collector.service; do
 [[ ! -e "$unit" ]] || { echo "ERRORE: servizio già esistente: $unit"; exit 1; }
done
for conf in /etc/apache2/sites-available/mmdvm-dashboard-mqtt.conf /etc/apache2/conf-available/mmdvm-dashboard-listen.conf; do
 [[ ! -e "$conf" ]] || { echo "ERRORE: configurazione Apache già esistente: $conf"; exit 1; }
done
[[ -f /etc/debian_version ]] || { echo 'Richiesto Debian/Raspberry Pi OS'; exit 1; }
command -v systemctl >/dev/null || { echo 'systemd richiesto'; exit 1; }
command -v apt-get >/dev/null || { echo 'apt richiesto'; exit 1; }
read -r -p 'Nominativo ripetitore [MMDVM]: ' CALLSIGN; CALLSIGN=${CALLSIGN:-MMDVM}
read -r -p 'Broker MQTT [127.0.0.1]: ' HOST; HOST=${HOST:-127.0.0.1}
read -r -p 'Porta MQTT [1883]: ' MQTT_PORT; MQTT_PORT=${MQTT_PORT:-1883}
read -r -p 'Topic MQTT [mmdvm/+/json]: ' TOPIC; TOPIC=${TOPIC:-mmdvm/+/json}
read -r -p 'Percorso MMDVM.ini (solo lettura) [/etc/MMDVM.ini]: ' MMDVM_INI; MMDVM_INI=${MMDVM_INI:-/etc/MMDVM.ini}
read -r -p 'Porta HTTPS dedicata [8443]: ' HTTPS_PORT; HTTPS_PORT=${HTTPS_PORT:-8443}
[[ $MQTT_PORT =~ ^[0-9]+$ ]] && ((MQTT_PORT>=1 && MQTT_PORT<=65535)) || { echo 'Porta MQTT non valida'; exit 1; }
[[ $HTTPS_PORT =~ ^[0-9]+$ ]] && ((HTTPS_PORT>=1024 && HTTPS_PORT<=65535)) || { echo 'Porta HTTPS non valida'; exit 1; }
[[ $HOST =~ ^[A-Za-z0-9._:-]+$ ]] || { echo 'Host MQTT non valido'; exit 1; }
[[ $TOPIC != *$'\n'* && -n $TOPIC ]] || { echo 'Topic non valido'; exit 1; }
[[ $CALLSIGN =~ ^[A-Za-z0-9-]+$ ]] || { echo 'Nominativo non valido'; exit 1; }
[[ $MMDVM_INI = /* && $MMDVM_INI != *$'\n'* ]] || { echo 'Percorso MMDVM.ini non valido'; exit 1; }
[[ -r "$MMDVM_INI" ]] || echo 'AVVISO: MMDVM.ini non leggibile ora; alcuni dati non saranno disponibili.'
if command -v ss >/dev/null; then
 for port in "$HTTPS_PORT" 8089; do
  if ss -H -ltn "sport = :$port" | grep -q .; then echo "Porta $port già occupata"; exit 1; fi
 done
fi
read -r -p 'Confermi installazione SOLO dashboard (s/N)? ' CONFIRM
[[ $CONFIRM == [sS] ]] || exit 0
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
import os,json,configparser
from pathlib import Path
root=Path(os.environ['APP'])
p=root/'config/dashboard.ini'
c=configparser.ConfigParser(interpolation=None);c.read(p)
c.set('repeater','callsign',os.environ['CALLSIGN'])
m=Path(os.environ['MMDVM_INI']);c.set('paths','mmdvm_dir',str(m.parent));c.set('paths','mmdvm_file',m.name)
with p.open('w') as f:c.write(f)
q=root/'data/mqtt-settings.json'
q.write_text(json.dumps(dict(host=os.environ['HOST'],port=int(os.environ['MQTT_PORT']),topic=os.environ['TOPIC'],username='',password='',tls=False),indent=2)+'\n')
q.chmod(0o600)
PYSET
chown root:"$SERVICE_USER" "$APP/config/dashboard.ini"
chmod 0660 "$APP/config/dashboard.ini"
chown "$SERVICE_USER:$SERVICE_USER" "$APP/data/mqtt-settings.json"
if [[ ! -f "$STATE/session-secret" ]]; then openssl rand -hex 32 > "$STATE/session-secret"; fi
if [[ ! -f "$STATE/admin.json" && ! -f "$STATE/setup-token" ]]; then openssl rand -hex 24 > "$STATE/setup-token"; fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$STATE"; chmod 0750 "$STATE"; chmod 0600 "$STATE"/*
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
# Dedicated SSL listener and vhost; do not overwrite existing websites.
[[ ! -e /etc/apache2/sites-available/mmdvm-dashboard-mqtt.conf ]] || { echo 'Sito Apache dashboard già presente'; exit 1; }
install -d -m 0755 /etc/ssl/mmdvm-dashboard
if [[ ! -f /etc/ssl/mmdvm-dashboard/cert.pem ]]; then
 openssl req -x509 -nodes -newkey rsa:2048 -days 365 -subj '/CN=mmdvm-dashboard.local' \
  -keyout /etc/ssl/mmdvm-dashboard/key.pem -out /etc/ssl/mmdvm-dashboard/cert.pem >/dev/null 2>&1
 chmod 0600 /etc/ssl/mmdvm-dashboard/key.pem
fi
cat > /etc/apache2/conf-available/mmdvm-dashboard-listen.conf <<EOF
Listen $HTTPS_PORT
EOF
cat > /etc/apache2/sites-available/mmdvm-dashboard-mqtt.conf <<EOF
<VirtualHost *:$HTTPS_PORT>
 ServerName localhost
 SSLEngine on
 SSLCertificateFile /etc/ssl/mmdvm-dashboard/cert.pem
 SSLCertificateKeyFile /etc/ssl/mmdvm-dashboard/key.pem
 ProxyPreserveHost On
 RequestHeader set X-Forwarded-Proto "https"
 ProxyPass / http://127.0.0.1:8089/
 ProxyPassReverse / http://127.0.0.1:8089/
 ErrorLog \${APACHE_LOG_DIR}/mmdvm-dashboard-error.log
 CustomLog \${APACHE_LOG_DIR}/mmdvm-dashboard-access.log combined
</VirtualHost>
EOF
a2enmod ssl proxy proxy_http headers >/dev/null
a2enconf mmdvm-dashboard-listen >/dev/null
a2ensite mmdvm-dashboard-mqtt >/dev/null
apache2ctl configtest
systemctl daemon-reload
systemctl enable --now mmdvm-mqtt-collector.service mmdvm-dashboard-mqtt.service
systemctl reload apache2 || systemctl restart apache2
printf '\nInstallazione completata. Apri https://IP-SERVER:%s/\n' "$HTTPS_PORT"
echo 'Token primo accesso (solo localmente): /var/lib/mmdvm-dashboard/setup-token'
echo 'Verifica: systemctl status mmdvm-dashboard-mqtt mmdvm-mqtt-collector'
