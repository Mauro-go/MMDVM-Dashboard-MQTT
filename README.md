# MMDVM Dashboard MQTT

**[Italiano](#italiano) | [English](#english)**

Dashboard web per ripetitori radioamatoriali MMDVMHost con telemetria MQTT, pannello di amministrazione e notifiche Telegram.

Web dashboard for amateur-radio repeaters running MMDVMHost with MQTT telemetry, an administration panel, and Telegram notifications.

> **Important / Importante:** This project is for MMDVMHost installations **already publishing MQTT messages**. It does not install or configure MMDVMHost or an MQTT broker. / Questo progetto richiede MMDVMHost **già configurato per pubblicare messaggi MQTT**. Non installa né configura MMDVMHost o il broker MQTT.

---

## Italiano

### Panoramica

**MMDVM Dashboard MQTT** è un'interfaccia web indipendente per visualizzare lo stato e l'attività di un ripetitore radioamatoriale. Un servizio raccoglie gli eventi pubblicati da MMDVMHost via MQTT e li rende disponibili al backend della dashboard.

Questo progetto è distinto dalla [MMDVM Dashboard originale (senza MQTT)](https://github.com/Mauro-go/MMDVM-Dashboard). La versione MQTT non si basa sulla lettura dei file di log per ricostruire le trasmissioni.

### Funzionalità

- **Dashboard in tempo reale:** visualizzazione delle informazioni sul ripetitore, attività radio e dati ricevuti via MQTT.
- **Informazioni di sistema:** CPU, memoria, disco, temperatura e uptime, quando disponibili.
- **Stato dei servizi:** rilevamento dei servizi radio/gateway installati e relativo stato systemd.
- **Pannello amministrativo protetto:** autenticazione, configurazione della dashboard e impostazioni MQTT.
- **MQTT configurabile:** host, porta, topic, credenziali e TLS gestibili dal pannello amministrativo.
- **Notifiche Telegram:** invio di avvisi per l'attività radio, con filtri personalizzabili.
- **Interfaccia italiano/inglese** e installazione guidata con selezione iniziale della lingua.
- **Servizi systemd dedicati** per backend, raccolta MQTT e bot Telegram.

Le informazioni mostrate dipendono dai messaggi MQTT effettivamente pubblicati, dalle modalità abilitate e dai servizi presenti sul sistema.

### Requisiti

- Debian 12/13 o Raspberry Pi OS basato su Debian, con `systemd` e `apt`.
- Privilegi `root` per l'installazione.
- MMDVMHost già installato e configurato per pubblicare gli eventi MQTT.
- Broker MQTT esistente, locale oppure remoto, raggiungibile dalla macchina.
- Apache HTTP Server, installato automaticamente se assente.
- Accesso alla rete per l'installazione dei pacchetti e, se si abilita Telegram, per raggiungere l'API Telegram.

L'installer installa le dipendenze Python tramite i pacchetti di sistema: Flask, Werkzeug, `psutil` e `paho-mqtt`.

### Installazione da zero

Scarica il repository sul server di destinazione, entra nella directory del progetto ed esegui:

```bash
sudo bash install.sh
```

L'installer richiede la scelta della lingua (**English** o **Italiano**) e poi:

1. Nominativo del ripetitore.
2. Indirizzo e porta del broker MQTT.
3. Topic MQTT pubblicato da MMDVMHost.
4. Percorso di `MMDVM.ini`, utilizzato in **sola lettura**.
5. Conferma esplicita prima di procedere.

L'installer è pensato per **nuove installazioni**: se trova un'installazione già presente, si interrompe invece di sovrascriverla.

#### Apache, frontend e siti già presenti

**Il file `index.html` viene installato esattamente in `/var/www/html/index.html`.** Anche gli altri file statici della directory `frontend/` vengono copiati in `/var/www/html/`, mantenendo le sottodirectory.

Il programma **non crea un nuovo VirtualHost, non aggiunge porte di ascolto e non modifica le direttive `DocumentRoot`**. Apache continua a servire il frontend statico dalla configurazione web esistente.

L'installer aggiunge una configurazione Apache separata, `mmdvm-dashboard-mqtt-api.conf`, che inoltra **soltanto `/api/`** al backend locale sulla porta `8089`. Il pannello amministrativo è raggiungibile sotto `/api/admin/`. Questa regola è globale per Apache, quindi si applica ai VirtualHost presenti: **prima di installare verifica che nessun altro sito utilizzi `/api/`**. Lo script verifica i conflitti evidenti nella configurazione Apache e si interrompe quando ne rileva uno.

Se un file web esiste già, l'installer elenca i conflitti, richiede una conferma e crea backup datati prima di sostituire i file. Gli altri file e le applicazioni già presenti non vengono eliminati.

**HTTPS:** per l'accesso amministrativo è necessario che Apache abbia già un sito HTTPS configurato. L'installer non crea certificati né modifica i VirtualHost SSL esistenti. Il pannello utilizza cookie di sessione sicuri e richiede richieste provenienti dalla stessa origine HTTPS.

### Accesso

Usa il **dominio HTTPS già configurato** sul server, senza aggiungere una porta dedicata:

| Funzione | Indirizzo |
| --- | --- |
| Dashboard | `https://TUO-DOMINIO/` |
| File principale | `/var/www/html/index.html` |
| Amministrazione | `https://TUO-DOMINIO/api/admin/` |
| API | `https://TUO-DOMINIO/api/` |

Gli indirizzi funzionano sul dominio il cui VirtualHost serve `/var/www/html`. Se la DocumentRoot del sito HTTPS è diversa, occorre predisporre manualmente la pubblicazione del frontend: l'installer non cambia la configurazione dei siti esistenti.

### Primo accesso amministrativo

Durante l'installazione viene creato un token per la configurazione iniziale dell'amministratore. Sul server, come `root`, è possibile leggerlo con:

```bash
cat /var/lib/mmdvm-dashboard/setup-token
```

Apri `/api/admin/` e completa la creazione dell'account amministrativo. La password deve contenere almeno **12 caratteri**. Il token di configurazione iniziale viene consumato dopo la creazione dell'account.

Non condividere il token, la password amministrativa o i file di configurazione privata.

### Notifiche Telegram

Il progetto include un **bot Telegram opzionale** che riceve gli eventi MQTT e può inviare notifiche a una chat Telegram. Il servizio `mmdvm-telegram-bot.service` viene installato insieme agli altri componenti, ma le notifiche restano disabilitate finché non vengono configurate e abilitate.

Per configurarlo:

1. Crea un bot tramite **@BotFather** su Telegram e conserva il token in modo riservato.
2. Recupera l'identificativo della chat (`chat_id`) destinataria.
3. Accedi al pannello Admin della dashboard e apri la sezione Telegram.
4. Inserisci il token e il `chat_id`, scegli i filtri desiderati e abilita le notifiche.
5. Verifica la ricezione di una trasmissione che soddisfi i filtri.

**Filtri disponibili:**

- **Modalità radio:** DMR, D-Star, YSF, P25, NXDN, FM e M17, in base agli eventi ricevuti.
- **Talkgroup DMR:** notifica tutti tranne quelli esclusi, oppure soltanto i talkgroup inclusi.
- **Nominativi esclusi:** elenco di callsign da ignorare.
- **Origine:** attività RF e/o rete.
- **Esclusione dei segnali orari** e dei beacon riconosciuti.
- **Durata minima** dell'attività da notificare.
- **Intervallo minimo** tra notifiche per limitare messaggi ripetitivi.

Le impostazioni vengono salvate in:

```text
/opt/mmdvm-dashboard-mqtt/data/telegram-settings.json
```

Il file contiene dati riservati, incluso il token del bot, e **non deve essere pubblicato su GitHub**. Il bot rilegge le impostazioni durante l'elaborazione degli eventi, quindi le modifiche ai filtri non richiedono normalmente un riavvio manuale.

La consegna delle notifiche richiede la connettività verso Telegram e dipende dagli eventi MQTT ricevuti.

### File e servizi principali

| Percorso / servizio | Descrizione |
| --- | --- |
| `/var/www/html/` | Frontend pubblicato da Apache |
| `/opt/mmdvm-dashboard-mqtt/backend/` | Backend API, collector e bot Telegram |
| `/opt/mmdvm-dashboard-mqtt/admin/` | Pagine dell'amministrazione |
| `/opt/mmdvm-dashboard-mqtt/config/dashboard.ini` | Configurazione generale |
| `/opt/mmdvm-dashboard-mqtt/data/mqtt-settings.json` | Configurazione MQTT riservata |
| `/opt/mmdvm-dashboard-mqtt/data/telegram-settings.json` | Configurazione Telegram riservata |
| `/opt/mmdvm-dashboard-mqtt/data/events.sqlite3` | Database degli eventi |
| `/var/lib/mmdvm-dashboard/` | Segreti di sessione e credenziali amministrative |
| `mmdvm-dashboard-mqtt.service` | Backend web/API |
| `mmdvm-mqtt-collector.service` | Raccolta eventi MQTT |
| `mmdvm-telegram-bot.service` | Bot notifiche Telegram |

### Diagnostica

Verifica lo stato dei servizi:

```bash
systemctl status mmdvm-dashboard-mqtt mmdvm-mqtt-collector mmdvm-telegram-bot
```

Controlla i log del backend, collector e bot:

```bash
journalctl -u mmdvm-dashboard-mqtt -n 50 --no-pager
journalctl -u mmdvm-mqtt-collector -n 50 --no-pager
journalctl -u mmdvm-telegram-bot -n 50 --no-pager
```

Controlla la configurazione Apache:

```bash
apache2ctl configtest
```

Se non vengono visualizzate trasmissioni, verifica prima che MMDVMHost pubblichi effettivamente sul broker e sul topic configurati. La dashboard non abilita MQTT in MMDVMHost.

### Sicurezza e aggiornamenti

- Non inserire nel repository token Telegram, password MQTT, database, credenziali amministrative o file di configurazione privata.
- L'installer non modifica né riavvia MMDVMHost, i gateway radio o il broker MQTT.
- Il percorso di `MMDVM.ini` viene utilizzato per la lettura; il file non viene modificato.
- L'installer descritto è destinato alle nuove installazioni; **non è uno script di aggiornamento** per impianti esistenti.
- Prima di installare su un ripetitore in produzione, prova la procedura in un ambiente di test e verifica gli eventuali conflitti con siti web esistenti.

---

## English

### Overview

**MMDVM Dashboard MQTT** is a standalone web interface for monitoring amateur-radio repeaters. A collector receives the events published by MMDVMHost through MQTT and makes them available to the dashboard backend.

This project is separate from the [original MMDVM Dashboard (without MQTT)](https://github.com/Mauro-go/MMDVM-Dashboard). The MQTT edition does not rely on parsing log files to reconstruct transmissions.

### Features

- **Live dashboard:** repeater information, radio activity and data received over MQTT.
- **System monitoring:** CPU, memory, disk usage, temperature and uptime where available.
- **Service status:** detection and systemd status of installed radio/gateway services.
- **Protected administration panel:** authentication, dashboard settings and MQTT configuration.
- **Configurable MQTT:** broker host, port, topic, credentials and TLS settings.
- **Telegram notifications:** radio activity alerts with configurable filters.
- **English/Italian interface** and an installer with initial language selection.
- **Dedicated systemd services** for the backend, MQTT collector and Telegram bot.

Displayed information depends on the MQTT messages actually published, the enabled radio modes and the services available on the host.

### Requirements

- Debian 12/13 or Debian-based Raspberry Pi OS with `systemd` and `apt`.
- `root` privileges for installation.
- MMDVMHost already installed and configured to publish MQTT events.
- An existing MQTT broker, local or remote, reachable from the host.
- Apache HTTP Server, installed automatically if missing.
- Network access for package installation and, when Telegram is enabled, access to the Telegram API.

The installer installs Python dependencies from system packages: Flask, Werkzeug, `psutil` and `paho-mqtt`.

### Fresh installation

Download the repository to the target server, enter the project directory and run:

```bash
sudo bash install.sh
```

The installer first asks for the language (**English** or **Italiano**), followed by:

1. Repeater callsign.
2. MQTT broker address and port.
3. MQTT topic published by MMDVMHost.
4. `MMDVM.ini` path, used in **read-only** mode.
5. Explicit confirmation before installation.

The installer is designed for **new installations**. It stops if it detects an existing dashboard installation rather than overwriting it.

#### Apache, frontend and existing websites

**`index.html` is installed at exactly `/var/www/html/index.html`.** All other static files from `frontend/` are copied into `/var/www/html/`, preserving their subdirectories.

The installer **does not create a VirtualHost, add listening ports or modify any `DocumentRoot` directive**. Apache continues serving the static frontend using the existing website configuration.

A separate Apache configuration, `mmdvm-dashboard-mqtt-api.conf`, forwards **only `/api/`** to the local backend on port `8089`. The administration panel is available under `/api/admin/`. This Apache-level rule is global and applies to existing VirtualHosts: **check that no other website uses `/api/`** before installation. The installer checks for obvious Apache configuration conflicts and stops when one is detected.

If web files already exist, the installer lists collisions, requests approval and creates timestamped backups before replacing files. Other files and applications are not deleted.

**HTTPS:** administrator access requires an existing Apache HTTPS website. The installer does not create certificates or modify existing SSL VirtualHosts. The administration panel uses secure session cookies and requires same-origin HTTPS requests.

### Access URLs

Use the server's **existing HTTPS domain**, without a dedicated dashboard port:

| Function | URL |
| --- | --- |
| Dashboard | `https://YOUR-DOMAIN/` |
| Main file | `/var/www/html/index.html` |
| Administration | `https://YOUR-DOMAIN/api/admin/` |
| API | `https://YOUR-DOMAIN/api/` |

These URLs work on the domain whose VirtualHost serves `/var/www/html`. If the HTTPS site's DocumentRoot differs, frontend publication must be configured separately: the installer does not alter existing websites.

### First-time administrator setup

The installer creates an initial administrator setup token. Read it locally as `root`:

```bash
cat /var/lib/mmdvm-dashboard/setup-token
```

Open `/api/admin/` and complete administrator account creation. The administrator password must contain at least **12 characters**. The setup token is consumed when the account is created.

Never share the setup token, administrator password or private configuration files.

### Telegram notifications

An **optional Telegram bot** listens to MQTT events and can send activity notifications to a Telegram chat. The `mmdvm-telegram-bot.service` unit is installed alongside the other services, but notifications remain disabled until configured and enabled.

To set it up:

1. Create a bot using **@BotFather** on Telegram and keep its token private.
2. Obtain the destination chat ID (`chat_id`).
3. Sign in to the dashboard Admin panel and open the Telegram section.
4. Enter the bot token and chat ID, select the desired filters and enable notifications.
5. Confirm that a qualifying transmission generates a notification.

**Available filters:**

- **Radio modes:** DMR, D-Star, YSF, P25, NXDN, FM and M17, depending on incoming events.
- **DMR talkgroups:** all except excluded talkgroups, or only explicitly included talkgroups.
- **Excluded callsigns:** ignore selected stations.
- **Event source:** RF and/or network.
- **Time-signal and beacon exclusion** when recognized.
- **Minimum event duration** before sending an alert.
- **Minimum gap** between notifications to reduce repeated messages.

Settings are stored in:

```text
/opt/mmdvm-dashboard-mqtt/data/telegram-settings.json
```

This file contains sensitive information, including the bot token, and **must never be committed to GitHub**. The bot reloads settings while processing events, so filter changes normally do not require a manual restart.

Delivery requires connectivity to Telegram and depends on the MQTT events received.

### Main paths and services

| Path / service | Purpose |
| --- | --- |
| `/var/www/html/` | Frontend served by Apache |
| `/opt/mmdvm-dashboard-mqtt/backend/` | API backend, collector and Telegram bot |
| `/opt/mmdvm-dashboard-mqtt/admin/` | Administration pages |
| `/opt/mmdvm-dashboard-mqtt/config/dashboard.ini` | General configuration |
| `/opt/mmdvm-dashboard-mqtt/data/mqtt-settings.json` | Private MQTT configuration |
| `/opt/mmdvm-dashboard-mqtt/data/telegram-settings.json` | Private Telegram configuration |
| `/opt/mmdvm-dashboard-mqtt/data/events.sqlite3` | Events database |
| `/var/lib/mmdvm-dashboard/` | Session secrets and administrator credentials |
| `mmdvm-dashboard-mqtt.service` | Web/API backend |
| `mmdvm-mqtt-collector.service` | MQTT event collector |
| `mmdvm-telegram-bot.service` | Telegram notification bot |

### Troubleshooting

Check the services:

```bash
systemctl status mmdvm-dashboard-mqtt mmdvm-mqtt-collector mmdvm-telegram-bot
```

Inspect backend, collector and bot logs:

```bash
journalctl -u mmdvm-dashboard-mqtt -n 50 --no-pager
journalctl -u mmdvm-mqtt-collector -n 50 --no-pager
journalctl -u mmdvm-telegram-bot -n 50 --no-pager
```

Validate Apache configuration:

```bash
apache2ctl configtest
```

If transmissions are missing, first verify that MMDVMHost is actually publishing to the configured broker and topic. The dashboard does not enable MQTT in MMDVMHost.

### Security and upgrades

- Never commit Telegram tokens, MQTT passwords, databases, administrator credentials or private configuration files.
- The installer does not modify or restart MMDVMHost, radio gateways or the MQTT broker.
- `MMDVM.ini` is read for information only; it is not modified.
- This installer is intended for fresh installations; **it is not an upgrade script** for existing systems.
- Test the procedure on a non-production host and review any website file collisions before deploying on an active repeater.

---

## Project links

- **MQTT edition:** https://github.com/Mauro-go/MMDVM-Dashboard-MQTT
- **Original non-MQTT edition:** https://github.com/Mauro-go/MMDVM-Dashboard

<img width="1917" height="1077" alt="Screenshot MMDVM Dashboard MQTT" src="https://github.com/user-attachments/assets/3a8af506-f042-42d1-a3e5-58cbe43487f2" />
