#!/usr/bin/env bash
# MMDVM Dashboard MQTT - HTTPS setup for fresh installations
set -Eeuo pipefail
umask 077

# HTTPS_BILINGUAL_V1
LANGUAGE="${LANGUAGE:-en}"
[[ "$LANGUAGE" == it ]] || LANGUAGE=en

msg() {
    if [[ "$LANGUAGE" == it ]]; then
        printf '%s\n' "$2"
    else
        printf '%s\n' "$1"
    fi
}

HTTPS_NAME="${1:-}"
WEBROOT="${2:-/var/www/html}"
SITE="mmdvm-dashboard-mqtt-ssl"
CERTDIR="/etc/apache2/ssl/mmdvm-dashboard-mqtt"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || die "$(msg "Root required." "Sono necessari i privilegi root.")"
[[ -n "$HTTPS_NAME" ]] || die "Usage: $0 IP-or-hostname [webroot]"
[[ -d /etc/apache2 ]] || die "$(msg "Apache is not installed." "Apache non è installato.")"
[[ -d "$WEBROOT" ]] || die "Webroot not found: $WEBROOT"

[[ "$HTTPS_NAME" =~ ^[A-Za-z0-9._:-]+$ ]] ||
    die "Invalid IP or hostname"

command -v openssl >/dev/null || die "$(msg "OpenSSL missing." "OpenSSL non installato.")"
command -v apache2ctl >/dev/null || die "$(msg "Apache missing." "Apache non disponibile.")"

# Do not create a competing HTTPS VirtualHost.
if apache2ctl -S 2>&1 | grep -Eq '(^|[[:space:]])(\*:443|[0-9a-fA-F.:]+:443)[[:space:]]'; then
    msg "Existing HTTPS VirtualHost detected." "VirtualHost HTTPS esistente rilevato."
    msg "Preserving existing HTTPS configuration." "La configurazione HTTPS esistente sarà conservata."
    # HTTPS_RESULT_FILE_V2
    if [[ -n "${HTTPS_RESULT_FILE:-}" ]]; then
        printf '%s\n' reused > "$HTTPS_RESULT_FILE"
    fi
    echo "HTTPS_REUSED=1"
    exit 0
fi

CONF="/etc/apache2/sites-available/${SITE}.conf"

[[ ! -e "$CONF" ]] || die "Site configuration already exists: $CONF"
[[ ! -e "$CERTDIR" ]] || die "Certificate directory already exists: $CERTDIR"

# Avoid interfering with another service on port 443.
if command -v ss >/dev/null; then
    if ss -H -ltn 'sport = :443' | grep -q .; then
        die "Port 443 already in use without an Apache HTTPS VirtualHost"
    fi
fi

# HTTPS_PREPARE_ROLLBACK_V1
# Remove only resources created during this invocation.
HTTPS_PREPARED=0
https_prepare_cleanup() {
    local rc=$?
    if (( rc != 0 )) && (( HTTPS_PREPARED == 1 )); then
        rm -f -- "$CONF"
        rm -rf -- "$CERTDIR"
        msg "HTTPS preparation rolled back." \
            "Preparazione HTTPS annullata; file creati rimossi." >&2
    fi
}
trap https_prepare_cleanup EXIT

install -d -m 0700 "$CERTDIR"
HTTPS_PREPARED=1

if [[ "$HTTPS_NAME" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ||
      "$HTTPS_NAME" == *:* ]]; then
    SAN="IP:$HTTPS_NAME"
else
    SAN="DNS:$HTTPS_NAME"
fi

openssl req -x509 -nodes -newkey rsa:3072 \
    -sha256 -days 825 \
    -keyout "$CERTDIR/server.key" \
    -out "$CERTDIR/server.crt" \
    -subj "/CN=$HTTPS_NAME" \
    -addext "subjectAltName=$SAN" >/dev/null 2>&1

chmod 0600 "$CERTDIR/server.key"
chmod 0644 "$CERTDIR/server.crt"

cat > "$CONF" <<EOF
<VirtualHost *:443>
    ServerName $HTTPS_NAME
    DocumentRoot $WEBROOT

    SSLEngine on
    SSLCertificateFile $CERTDIR/server.crt
    SSLCertificateKeyFile $CERTDIR/server.key

    # HTTPS_PROXY_GLOBAL_V1: /api/ is configured by install.sh

    <Directory "$WEBROOT">
        Require all granted
    </Directory>

    ErrorLog \${APACHE_LOG_DIR}/mmdvm-dashboard-ssl-error.log
    CustomLog \${APACHE_LOG_DIR}/mmdvm-dashboard-ssl-access.log combined
</VirtualHost>
EOF

# Validate the candidate configuration without enabling it yet.
apache2ctl configtest >/dev/null ||
    die "Existing Apache configuration is invalid"

msg "HTTPS configuration prepared:" "Configurazione HTTPS preparata:"
echo "  Site: $CONF"
msg "  Certificate: $CERTDIR/server.crt" "  Certificato: $CERTDIR/server.crt"
if [[ -n "${HTTPS_RESULT_FILE:-}" ]]; then
    printf '%s\n' created > "$HTTPS_RESULT_FILE"
fi
echo "  HTTPS_REUSED=0"
msg "The site has NOT been enabled." "Il sito NON è stato ancora abilitato."
