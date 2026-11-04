#!/usr/bin/env bash
# MMDVM Dashboard MQTT - prepare HTTPS for a fresh installation (EN/IT)
set -Eeuo pipefail
umask 077
LANGUAGE=${LANGUAGE:-en}; [[ $LANGUAGE == it ]] || LANGUAGE=en
msg() { if [[ $LANGUAGE == it ]]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
die() { msg "$1" "$2" >&2; exit 1; }
HTTPS_NAME=${1:-}; WEBROOT=${2:-/var/www/html}
SITE=mmdvm-dashboard-mqtt-ssl
CONF=/etc/apache2/sites-available/${SITE}.conf
CERTDIR=/etc/apache2/ssl/mmdvm-dashboard-mqtt
[[ $EUID -eq 0 ]] || die 'Root required.' 'Sono necessari i privilegi root.'
[[ -n $HTTPS_NAME ]] || die 'Usage: setup-https.sh IP-or-hostname [webroot]' 'Uso: setup-https.sh IP-o-hostname [directory-web]'
[[ -d /etc/apache2 && -d $WEBROOT ]] || die 'Apache or webroot not found.' 'Apache o directory web non trovati.'
command -v openssl >/dev/null && command -v apache2ctl >/dev/null && command -v python3 >/dev/null || die 'Missing OpenSSL, Apache or Python.' 'Mancano OpenSSL, Apache o Python.'
# Strict hostname/IP validation; prevents Apache directive and X.509 SAN injection.
SAN=$(python3 - "$HTTPS_NAME" <<'PY'
import ipaddress,re,sys
n=sys.argv[1]
try:
    print('IP:'+str(ipaddress.ip_address(n)))
except ValueError:
    labels=n.split('.')
    if len(n)>253 or not labels or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',x) for x in labels):
        sys.exit(1)
    print('DNS:'+n)
PY
) || die 'Invalid HTTPS IP/hostname.' 'IP/nome host HTTPS non valido.'
# Check Apache's current configuration BEFORE creating anything.
apache2ctl configtest >/dev/null || die 'Existing Apache configuration is invalid.' 'La configurazione Apache esistente non è valida.'
# A pre-existing HTTPS vhost is never edited. Require requested name to appear
# in Apache's vhost listing, rather than silently reusing an unrelated site.
VHOSTS=$(apache2ctl -S 2>&1) || die 'Cannot inspect Apache VirtualHosts.' 'Impossibile controllare i VirtualHost Apache.'
if grep -Eq '(^|[[:space:]])(\*:443|\[[^]]+\]:443|[0-9a-fA-F.:]+:443)([[:space:]]|$)' <<<"$VHOSTS"; then
    if ! grep -Fi -- "$HTTPS_NAME" <<<"$VHOSTS" >/dev/null; then
        die 'HTTPS already exists for a different name. Configure its routing manually.' 'HTTPS esiste già per un altro nome. Configurare manualmente il collegamento.'
    fi
    msg 'Matching HTTPS VirtualHost found; preserving it.' 'VirtualHost HTTPS corrispondente trovato; verrà conservato.'
    [[ -z ${HTTPS_RESULT_FILE:-} ]] || printf 'reused\n' > "$HTTPS_RESULT_FILE"
    exit 0
fi
[[ ! -e $CONF && ! -L $CONF ]] || die 'HTTPS site configuration already exists.' 'La configurazione del sito HTTPS esiste già.'
[[ ! -e $CERTDIR && ! -L $CERTDIR ]] || die 'Certificate directory already exists.' 'La directory dei certificati esiste già.'
if command -v ss >/dev/null && ss -H -ltn 'sport = :443' | grep -q .; then
    die 'Port 443 is already in use.' 'La porta 443 è già occupata.'
fi
CREATED=0
cleanup() {
    local rc=$?
    trap - EXIT
    if (( rc != 0 && CREATED == 1 )); then
        rm -f -- "$CONF"
        rm -f -- "$CERTDIR/server.key" "$CERTDIR/server.crt"
        rmdir -- "$CERTDIR" 2>/dev/null || true
        msg 'HTTPS preparation rolled back.' 'Preparazione HTTPS annullata.' >&2
    fi
    exit "$rc"
}
trap cleanup EXIT
mkdir -m 0700 -- "$CERTDIR"
CREATED=1
openssl req -x509 -nodes -newkey rsa:3072 -sha256 -days 825 \
    -keyout "$CERTDIR/server.key" -out "$CERTDIR/server.crt" \
    -subj "/CN=$HTTPS_NAME" -addext "subjectAltName=$SAN" >/dev/null 2>&1
chmod 0600 "$CERTDIR/server.key"
chmod 0644 "$CERTDIR/server.crt"
cat > "$CONF" <<VHOST
<VirtualHost *:443>
    ServerName $HTTPS_NAME
    DocumentRoot "$WEBROOT"
    SSLEngine on
    SSLCertificateFile $CERTDIR/server.crt
    SSLCertificateKeyFile $CERTDIR/server.key
    <Directory "$WEBROOT">
        Require all granted
    </Directory>
    ErrorLog \${APACHE_LOG_DIR}/mmdvm-dashboard-ssl-error.log
    CustomLog \${APACHE_LOG_DIR}/mmdvm-dashboard-ssl-access.log combined
</VirtualHost>
VHOST
# Result is only written once both certificate and site configuration exist.
[[ -z ${HTTPS_RESULT_FILE:-} ]] || printf 'created\n' > "$HTTPS_RESULT_FILE"
msg 'HTTPS site prepared (not enabled yet).' 'Sito HTTPS preparato (non ancora abilitato).'
