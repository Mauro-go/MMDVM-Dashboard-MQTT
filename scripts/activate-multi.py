#!/usr/bin/env python3
"""Activate the independent Multi copy on this VM, retaining rollback files."""
import configparser
import datetime
import grp
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import ssl
import subprocess
import time
import urllib.request

ROOT=Path('/opt/MMDVM-Dashboard-MQTT-Multi')
assert Path.cwd()==ROOT and os.geteuid()==0
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
backup=ROOT/'data'/'deployment-backups'/stamp
backup.mkdir(parents=True,mode=0o700)
paths=[Path('/etc/apache2/sites-available/mmdvm-dashboard-mqtt-ssl.conf'),Path('/etc/apache2/sites-available/000-default.conf'),Path('/etc/apache2/conf-available/mmdvm-dashboard-mqtt-api.conf')]
paths.append(Path('/etc/apache2/conf-enabled/mmdvm-dashboard-mqtt-api.conf'))
for path in paths:
 shutil.copy2(path,backup/(path.parent.name+'--'+path.name))
old_enabled={name:subprocess.run(['systemctl','is-enabled',name],capture_output=True,text=True).stdout.strip()=='enabled' for name in ('mmdvm-dashboard-mqtt','mmdvm-mqtt-collector')}

def run(*args):
 subprocess.run(args,check=True)

user=pwd.getpwnam('mmdvm-dashboard')
group=grp.getgrnam('mmdvm-dashboard')
# Refresh the independent snapshot immediately before the cutover.
source=Path('/opt/mmdvm-dashboard-mqtt')
for name in ('mqtt-settings.json','agent-state.json','telegram-settings.json'):
 src=source/'data'/name
 if src.exists():
  shutil.copyfile(src,ROOT/'data'/name)
  os.chmod(ROOT/'data'/name,0o600)
if (source/'data'/'events.sqlite3').exists():
 src=sqlite3.connect((source/'data'/'events.sqlite3').as_uri()+'?mode=ro',uri=True)
 dst=sqlite3.connect(ROOT/'data'/'events.sqlite3')
 try:
  src.backup(dst)
 finally:
  dst.close();src.close()
for base in (ROOT/'data',ROOT/'config'):
 for current,dirs,files in os.walk(base):
  os.chown(current,user.pw_uid,group.gr_gid)
  for name in files:
   os.chown(Path(current)/name,user.pw_uid,group.gr_gid)
os.chmod(ROOT/'data',0o750)
os.chmod(ROOT/'config',0o2770)
common='''[Unit]
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=mmdvm-dashboard
Group=mmdvm-dashboard
WorkingDirectory={root}/backend
Environment=MMDVM_NODE_CONFIG={root}/config/dashboard.ini
Environment=MMDVM_NODE_DATA={root}/data
Environment=MMDVM_DASHBOARD_STATE_DIR={root}/data/main-admin
Environment=MMDVM_DASHBOARD_PORT=8090
ExecStart=/usr/bin/python3 -u {root}/backend/{entry}
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths={root}/data {root}/config
[Install]
WantedBy=multi-user.target
'''
new_units=('mmdvm-dashboard-multi','mmdvm-multi-collector')
try:
 for name,entry in zip(new_units,('app.py','mqtt_collector.py')):
  Path('/etc/systemd/system/'+name+'.service').write_text(common.format(root=ROOT,entry=entry))
 run('systemctl','daemon-reload')
 run('systemctl','enable','--now',*new_units)
 for attempt in range(60):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8090/',timeout=2) as response:
    assert 'multi-select' in response.read().decode()
    break
  except OSError:
   time.sleep(.2)
 else:
  raise RuntimeError('Multi backend did not become ready')
 ssl_site=paths[0].read_text()
 assert 'MULTI_ACTIVE' not in ssl_site,'Already activated'
 proxy='''    # MULTI_ACTIVE: all dashboard routes use the independent Multi backend.
    ProxyPassInherit Off
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8090/
    ProxyPassReverse / http://127.0.0.1:8090/
'''
 paths[0].write_text(ssl_site.replace('</VirtualHost>',proxy+'</VirtualHost>'))
 http_site=paths[1].read_text()
 paths[1].write_text(http_site.replace('</VirtualHost>','    # MULTI_ACTIVE: use the existing HTTPS dashboard.\n    Redirect temp / https://192.168.0.107/\n</VirtualHost>'))
 paths[2].write_text('ProxyPreserveHost On\nProxyPass /api/ http://127.0.0.1:8090/api/\nProxyPassReverse /api/ http://127.0.0.1:8090/api/\n')
 paths[3].write_text(paths[2].read_text())
 run('apachectl','configtest')
 run('systemctl','reload','apache2')
 time.sleep(2)
 context=ssl.create_default_context(cafile='/etc/apache2/ssl/mmdvm-dashboard-mqtt/server.crt')
 for path in ('/','/api/config','/api/multi/nodes','/api/admin/'):
  for attempt in range(40):
   try:
    with urllib.request.urlopen('https://192.168.0.107'+path,context=context,timeout=5) as response:
     assert response.status==200
     body=response.read()
     if path=='/':
      assert b'multi-select' in body
     print('HTTPS verified:',path)
     break
   except (OSError, AssertionError):
    if attempt==39:
     raise
    time.sleep(.25)
 run('systemctl','disable','--now','mmdvm-dashboard-mqtt','mmdvm-mqtt-collector')
 print('MULTI ACTIVE: https://192.168.0.107/')
 print('Rollback configuration:',backup)
except Exception:
 for path in paths:
  shutil.copy2(backup/(path.parent.name+'--'+path.name),path)
 subprocess.run(['apachectl','configtest'])
 subprocess.run(['systemctl','reload','apache2'])
 subprocess.run(['systemctl','disable','--now',*new_units])
 for name,enabled in old_enabled.items():
  subprocess.run(['systemctl','enable' if enabled else 'disable',name])
  subprocess.run(['systemctl','start',name])
 raise
