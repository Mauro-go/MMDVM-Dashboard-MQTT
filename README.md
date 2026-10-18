# MMDVM Dashboard MQTT — pacchetto generico (beta)

Dashboard web indipendente per ripetitori con **MMDVMHost già abilitato MQTT**. Non installa, modifica né riavvia MMDVMHost, MMDVM.ini o il broker MQTT.

## Installazione (su macchina di prova)

Requisiti: Debian 12/13 o Raspberry Pi OS basato su Debian, systemd, apt, root, broker MQTT già esistente. Non eseguire su un ripetitore in produzione senza test preliminari: il pacchetto è una **beta da verificare**.

```sh
sudo bash install.sh
```

L'installer chiede host, porta, topic MQTT, nominativo, posizione di MMDVM.ini **solo in lettura**, e porta HTTPS (default 8443). Installa Apache, Flask, psutil, paho-mqtt e i servizi dashboard, senza cambiare servizi radio. Per MQTT con password: dopo il primo accesso imposta le credenziali dal pannello Admin. Le password non sono mai salvate nel repository.

Accesso: `https://IP-DEL-SERVER:8443/` e `https://IP-DEL-SERVER:8443/api/admin/`. Il certificato iniziale è autofirmato: il browser mostrerà un avviso. Prima di esporre il servizio a Internet configura un certificato attendibile e controlla la sicurezza del server. Il token iniziale si legge localmente da `/var/lib/mmdvm-dashboard/setup-token` (root); viene consumato al primo setup. La password admin deve avere almeno 12 caratteri.

### Configurazione e dati

- `/opt/mmdvm-dashboard-mqtt/config/dashboard.ini`: impostazioni generali
- `/opt/mmdvm-dashboard-mqtt/data/mqtt-settings.json`: impostazioni MQTT private (0600)
- `/opt/mmdvm-dashboard-mqtt/data/events.sqlite3`: database eventi, non incluso nel pacchetto
- `/var/lib/mmdvm-dashboard`: segreto di sessione e credenziali amministratore
- `mmdvm-dashboard-mqtt.service`, `mmdvm-mqtt-collector.service`: soli servizi installati

La dashboard legge MMDVM.ini ma non lo modifica. Le informazioni di modalità e stato dei gateway dipendono da ciò che è installato e visibile all'utente dashboard. Il topic MQTT deve corrispondere a quello pubblicato dall'installazione radio.

### Limitazioni beta

Testare prima su una VM/Raspberry di prova; la procedura è per una **nuova installazione** e rifiuta di sovrascrivere una dashboard esistente. La riconfigurazione di un'installazione preesistente e il supporto a certificati personalizzati sono da completare. Il collector tenta la riconnessione e ricarica le impostazioni, ma un breve intervallo senza eventi può verificarsi durante un cambio broker. La dashboard non configura MMDVMHost.
