#!/usr/bin/env python3
"""Copy primary runtime data into this checkout without changing the source."""
import argparse
import configparser
import os
from pathlib import Path
import shutil
import sqlite3

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--state', type=Path, required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
source=args.source.resolve()
state=args.state.resolve()
if source==root:
    parser.error('Source must be a different installation')
for required in (source/'config'/'dashboard.ini',state/'session-secret'):
    if not required.is_file():
        parser.error('Missing source file: '+str(required))
config=root/'config'/'dashboard.ini'
data=root/'data'
admin=data/'main-admin'
if config.exists() or admin.exists() or (data/'events.sqlite3').exists():
    parser.error('Destination runtime already exists; no files were overwritten')
data.mkdir(exist_ok=True,mode=0o700)
admin.mkdir(mode=0o700)
for name in ('session-secret','admin.json','setup-token'):
    src=state/name
    if src.is_file():
        shutil.copyfile(src,admin/name)
        os.chmod(admin/name,0o600)
for name in ('mqtt-settings.json','telegram-settings.json','agent-state.json'):
    src=source/'data'/name
    if src.is_file():
        shutil.copyfile(src,data/name)
        os.chmod(data/name,0o600)
if (source/'data'/'databases').is_dir():
    shutil.copytree(source/'data'/'databases',data/'databases',dirs_exist_ok=False)
if (source/'data'/'events.sqlite3').is_file():
    source_db=sqlite3.connect((source/'data'/'events.sqlite3').as_uri()+'?mode=ro',uri=True)
    destination_db=sqlite3.connect(data/'events.sqlite3')
    try:
        source_db.backup(destination_db)
    finally:
        destination_db.close()
        source_db.close()
    os.chmod(data/'events.sqlite3',0o600)
cfg=configparser.ConfigParser(interpolation=None)
cfg.read(source/'config'/'dashboard.ini')
if cfg.has_section('paths'):
    for key,value in list(cfg['paths'].items()):
        old=str(source/'data')
        if value==old or value.startswith(old+'/'):
            cfg['paths'][key]=str(data)+value[len(old):]
with config.open('x') as handle:
    cfg.write(handle)
os.chmod(config,0o600)
print('Independent primary runtime prepared in '+str(root))
print('Source installation was read only. No services or web-server settings changed.')
