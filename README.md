# MMDVM Dashboard MQTT — Beta

[Italiano](#italiano) | [English](#english)

## Italiano

### Descrizione

**MMDVM Dashboard MQTT** è una dashboard web indipendente per il monitoraggio di ripetitori radioamatoriali che utilizzano **MMDVMHost già abilitato MQTT**. Raccoglie i dati pubblicati via MQTT e li presenta in un'interfaccia web con pannello di amministrazione protetto da autenticazione.

Il progetto deriva dall'esperienza della dashboard originale **[MMDVM Dashboard (senza MQTT)](https://github.com/Mauro-go/MMDVM-Dashboard)**. I due repository sono distinti: questa versione utilizza MQTT per la raccolta degli eventi, mentre il progetto originale non richiede MQTT.

La dashboard **non installa, modifica né riavvia MMDVMHost**, non modifica `MMDVM.ini` e non installa né riconfigura il broker MQTT.

### Funzionalità

- Visualizzazione web dello stato e dell'attività del ripetitore tramite MQTT.
- Pannello Admin con autenticazione per gestire le impostazioni della dashboard.
- Configurazione di host, porta, topic, credenziali e TLS MQTT dal pannello Admin.
- Interfaccia in italiano e inglese.
- Script di installazione per sistemi Debian compatibili.

### Installazione (solo su macchina di prova)

**Requisiti:** Debian 12/13 o Raspberry Pi OS basato su Debian, `systemd`, `apt`, privilegi `root`, un broker MQTT già esistente e MMDVMHost già configurato per pubblicare i dati MQTT.

**Attenzione:** questa è una **versione Beta non ancora verificata su un'installazione pulita**. Non eseguirla su un ripetitore in produzione senza test preliminari.

```sh
sudo bash install.sh
```

L'installer richiede host, porta e topic MQTT, nominativo, percorso di `MMDVM.ini` (**sola lettura**) e porta HTTPS (predefinita `8443`). Installa Apache, Flask, `psutil`, `paho-mqtt` e i servizi della dashboard, senza cambiare i servizi radio.

Se il broker MQTT richiede credenziali, configurale dal pannello Admin dopo il primo accesso. Le password non sono incluse nel repository.

**Indirizzi di accesso:**

- Dashboard: `https://IP-DEL-SERVER:8443/`
- API amministrazione: `https://IP-DEL-SERVER:8443/api/admin/`

Il certificato HTTPS iniziale è **autofirmato**, quindi il browser mostrerà un avviso. Prima di esporre il servizio a Internet, configura un certificato attendibile e verifica la sicurezza del server.

Il token per la configurazione iniziale dell'amministratore si legge localmente da `/var/lib/mmdvm-dashboard/setup-token` (accessibile a `root`) e viene consumato al primo setup. La password amministratore deve contenere almeno **12 caratteri**.

### Configurazione e dati

| Percorso o servizio | Funzione |
| --- | --- |
| `/opt/mmdvm-dashboard-mqtt/config/dashboard.ini` | Impostazioni generali |
| `/opt/mmdvm-dashboard-mqtt/data/mqtt-settings.json` | Impostazioni MQTT private (permessi `0600`) |
| `/opt/mmdvm-dashboard-mqtt/data/events.sqlite3` | Database degli eventi, escluso dal repository |
| `/var/lib/mmdvm-dashboard` | Segreto di sessione e credenziali amministratore |
| `mmdvm-dashboard-mqtt.service` | Servizio della dashboard |
| `mmdvm-mqtt-collector.service` | Servizio di raccolta MQTT |

La dashboard legge `MMDVM.ini` ma non lo modifica. Le informazioni sulle modalità e sullo stato dei gateway dipendono dai componenti installati e accessibili all'utente del servizio dashboard. Il topic MQTT deve corrispondere a quello pubblicato dall'installazione radio.

### Limitazioni della Beta

- L'installer è destinato a **nuove installazioni** e rifiuta di sovrascrivere una dashboard esistente.
- La riconfigurazione di un'installazione preesistente e il supporto ai certificati personalizzati devono ancora essere completati.
- Il collector tenta di riconnettersi e ricarica le impostazioni, ma durante un cambio di broker può verificarsi un breve intervallo senza eventi.
- La dashboard **non configura MMDVMHost**.

---

## English

### Overview

**MMDVM Dashboard MQTT** is a standalone web dashboard for monitoring amateur radio repeaters running **MMDVMHost with MQTT already enabled**. It collects data published over MQTT and displays it in a web interface with a password-protected administration panel.

This project builds on the original **[MMDVM Dashboard (without MQTT)](https://github.com/Mauro-go/MMDVM-Dashboard)**. The projects are available in separate repositories: this version uses MQTT to collect events, whereas the original project does not require MQTT.

The dashboard **does not install, modify, or restart MMDVMHost**. It does not modify `MMDVM.ini`, and it does not install or reconfigure the MQTT broker.

### Features

- Web-based repeater status and activity monitoring via MQTT.
- Authenticated administration panel for dashboard settings.
- MQTT host, port, topic, credentials, and TLS settings managed through the administration panel.
- Italian and English interface.
- Installation script for compatible Debian-based systems.

### Installation (test systems only)

**Requirements:** Debian 12/13 or Debian-based Raspberry Pi OS, `systemd`, `apt`, `root` privileges, an existing MQTT broker, and MMDVMHost already configured to publish MQTT data.

**Warning:** this is a **Beta release that has not yet been verified on a clean installation**. Do not deploy it on a production repeater without testing it first.

```sh
sudo bash install.sh
```

The installer asks for the MQTT host, port, and topic, repeater callsign, path to `MMDVM.ini` (**read-only**), and HTTPS port (default `8443`). It installs Apache, Flask, `psutil`, `paho-mqtt`, and the dashboard services without changing radio services.

If your MQTT broker requires authentication, enter its credentials in the Admin panel after the initial setup. Passwords are not included in the repository.

**Access URLs:**

- Dashboard: `https://SERVER-IP:8443/`
- Administration API: `https://SERVER-IP:8443/api/admin/`

The initial HTTPS certificate is **self-signed**, so your browser will display a warning. Before exposing the service to the Internet, configure a trusted certificate and review the server's security settings.

The initial administrator setup token can be read locally from `/var/lib/mmdvm-dashboard/setup-token` (accessible to `root`) and is consumed during the first setup. The administrator password must contain at least **12 characters**.

### Configuration and data

| Path or service | Purpose |
| --- | --- |
| `/opt/mmdvm-dashboard-mqtt/config/dashboard.ini` | General settings |
| `/opt/mmdvm-dashboard-mqtt/data/mqtt-settings.json` | Private MQTT settings (`0600` permissions) |
| `/opt/mmdvm-dashboard-mqtt/data/events.sqlite3` | Event database, excluded from the repository |
| `/var/lib/mmdvm-dashboard` | Session secret and administrator credentials |
| `mmdvm-dashboard-mqtt.service` | Dashboard service |
| `mmdvm-mqtt-collector.service` | MQTT collector service |

The dashboard reads `MMDVM.ini` but never modifies it. Mode and gateway status information depends on the components installed and accessible to the dashboard service account. The MQTT topic must match the topic published by the radio installation.

### Beta limitations

- The installer is intended for **new installations** and refuses to overwrite an existing dashboard.
- Reconfiguration of existing installations and custom certificate support are not yet complete.
- The collector attempts to reconnect and reload its settings, but switching brokers may cause a short gap in received events.
- The dashboard **does not configure MMDVMHost**.
