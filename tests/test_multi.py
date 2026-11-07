"""Run with python3 -m unittest discover -s tests -v (no broker required)."""
import configparser
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
TEMP = tempfile.TemporaryDirectory(prefix='mmdvm-multi-test-')
DIRECTORY = Path(TEMP.name)
(DIRECTORY / 'data').mkdir()
(DIRECTORY / 'admin').mkdir()
(DIRECTORY / 'admin' / 'session-secret').write_text(secrets.token_hex(32))
cfg = configparser.ConfigParser(interpolation=None)
cfg.read(ROOT / 'config' / 'dashboard.ini.example')
cfg['deployment'].update(mode='remote', node_id='rootnode', agent_topic_prefix='agents/rootnode')
with (DIRECTORY / 'dashboard.ini').open('w') as handle:
    cfg.write(handle)
os.environ.update(MMDVM_NODE_CONFIG=str(DIRECTORY / 'dashboard.ini'), MMDVM_NODE_DATA=str(DIRECTORY / 'data'), MMDVM_DASHBOARD_STATE_DIR=str(DIRECTORY / 'admin'), MMDVM_MULTI_TESTING='1')
from app import app
import auth
from multi_mqtt import accept_event
from werkzeug.security import generate_password_hash

PASSWORD = 'Test-only-password-482!'
auth.CREDENTIALS_FILE.write_text(json.dumps({'username':'rootadmin', 'password_hash':generate_password_hash(PASSWORD)}))

class MultiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = app.extensions['multi_registry']
        cls.client = app.test_client()
        cls.base = 'https://dashboard.test'
        response = cls.client.post('/api/admin/login', base_url=cls.base, json={'username':'rootadmin','password':PASSWORD}, headers={'Origin':cls.base})
        assert response.status_code == 200, response.get_data(as_text=True)
        session = cls.client.get('/api/admin/session', base_url=cls.base).get_json()
        cls.headers = {'Origin':cls.base, 'X-CSRF-Token':session['csrf_token']}
        for callsign in ('IR3ABC', 'IR3XYZ'):
            response = cls.client.post('/api/admin/multi', base_url=cls.base, json=cls.node(callsign), headers=cls.headers)
            assert response.status_code == 201, response.get_data(as_text=True)

    @classmethod
    def tearDownClass(cls):
        cls.registry.close()
        TEMP.cleanup()

    @staticmethod
    def node(callsign):
        slug = callsign.lower()
        return dict(callsign=callsign, node_id=slug, host='127.0.0.1', port=1883, topic='mmdvm/'+slug+'/json', agent_topic_prefix='agents/'+slug, admin_username=slug, admin_password=PASSWORD)

    def get(self, path):
        return self.client.get(path, base_url=self.base)

    def test_root_and_callsign_routes(self):
        self.assertEqual(self.get('/').status_code, 200)
        self.assertEqual(self.get('/api/config').status_code, 200)
        self.assertEqual(self.get('/ir3abc').status_code, 308)
        self.assertEqual(self.get('/ir3abc/').status_code, 200)
        self.assertEqual(self.get('/ir3xyz/').status_code, 200)
        self.assertEqual(self.get('/unknown-node/').status_code, 404)
        self.assertEqual(len(self.get('/api/multi/nodes').get_json()), 3)
        text = self.get('/ir3abc/').get_data(as_text=True)
        self.assertIn('/ir3abc/api/live', text)
        self.assertIn('multi-select', text)
        self.assertIn('/ir3abc/api/admin/', text)
        self.assertNotIn("fetch('/api/config')", text)

    def test_independent_admin_and_cookie_paths(self):
        self.assertFalse(self.get('/ir3abc/api/admin/session').get_json()['authenticated'])
        response = self.client.post('/ir3abc/api/admin/login', base_url=self.base, json={'username':'ir3abc','password':PASSWORD}, headers={'Origin':self.base})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('mmdvm_admin_ir3abc=', cookie)
        self.assertIn('Path=/ir3abc/', cookie)
        self.assertTrue(self.get('/ir3abc/api/admin/session').get_json()['authenticated'])
        self.assertFalse(self.get('/ir3xyz/api/admin/session').get_json()['authenticated'])
        self.assertTrue(self.get('/api/admin/session').get_json()['authenticated'])
        self.assertEqual(self.get('/ir3abc/api/admin/multi').status_code, 404)
        self.assertEqual(self.get('/ir3abc/admin/').status_code, 200)

    def test_management_authentication_csrf_and_origin(self):
        guest = app.test_client()
        self.assertEqual(guest.get('/api/admin/multi', base_url=self.base).status_code, 401)
        self.assertEqual(guest.get('/admin/multi/', base_url=self.base).status_code, 302)
        self.assertEqual(self.get('/admin/multi/').status_code, 200)
        self.assertEqual(self.client.post('/api/admin/multi', base_url=self.base, json=self.node('IR4ABC'), headers={'Origin':self.base}).status_code, 403)
        self.assertEqual(self.client.post('/api/admin/multi', base_url=self.base, json=self.node('IR4ABC'), headers={**self.headers, 'Origin':'https://evil.test'}).status_code, 403)

    def test_validation_and_duplicate_node_ids(self):
        for changes in ({'callsign':'../escape'}, {'callsign':'API'}, {'node_id':'rootnode'}, {'node_id':'ir3abc'}, {'topic':'mmdvm/+/json'}, {'topic':'mmdvm/ir3abc/json'}, {'agent_topic_prefix':'agents/ir3abc/nested'}, {'port':True}):
            data = self.node('IR4ABC') | changes
            response = self.client.post('/api/admin/multi', base_url=self.base, json=data, headers=self.headers)
            self.assertEqual(response.status_code, 400, (changes, response.get_data(as_text=True)))
        self.assertEqual(len(self.registry.read()), 2)


    def test_node_admin_cannot_rebind_identity_or_topics(self):
        client = app.test_client()
        login = client.post('/ir3xyz/api/admin/login', base_url=self.base, json={'username':'ir3xyz','password':PASSWORD}, headers={'Origin':self.base})
        self.assertEqual(login.status_code, 200)
        token = client.get('/ir3xyz/api/admin/session', base_url=self.base).get_json()['csrf_token']
        headers = {'Origin':self.base,'X-CSRF-Token':token}
        for payload in ({'deployment':{'node_id':'ir3abc'}}, {'deployment':{'mode':'local'}}, {'deployment':{'agent_topic_prefix':'agents/ir3abc'}}):
            result = client.post('/ir3xyz/api/admin/config', base_url=self.base, json=payload, headers=headers)
            self.assertEqual(result.status_code, 400)
        result = client.post('/ir3xyz/api/admin/mqtt', base_url=self.base, json={'topic':'mmdvm/ir3abc/json'}, headers=headers)
        self.assertEqual(result.status_code, 400)
        for path,payload in (('/api/admin/config',{'deployment':{'node_id':'ir3abc'}}), ('/api/admin/mqtt',{'topic':'mmdvm/ir3abc/json'})):
            result = self.client.post(path, base_url=self.base, json=payload, headers=self.headers)
            self.assertEqual(result.status_code, 400)

    def test_collector_stores_only_its_node_events(self):
        import subprocess
        script = '''
import json,types
from mqtt_store import connect
from mqtt_collector import on_message
con=connect()
def event(topic, node):
    payload=json.dumps({'DMR':{'node_id':node,'action':'test','timestamp':'2026-11-07T12:00:00Z'}}).encode()
    on_message(None, {'db':con}, types.SimpleNamespace(topic=topic,payload=payload))
event('mmdvm/ir3abc/json','ir3abc')
event('mmdvm/ir3xyz/json','ir3xyz')
event('mmdvm/ir3abc/json','ir3xyz')
assert con.execute('SELECT count(*) FROM events WHERE action="test"').fetchone()[0] == 1
con.close()
'''
        directory = self.registry.directory / 'ir3abc'
        env = dict(os.environ, MMDVM_MULTI_WORKER='ir3abc', MMDVM_NODE_CONFIG=str(directory/'dashboard.ini'), MMDVM_NODE_DATA=str(directory/'data'), MMDVM_DASHBOARD_STATE_DIR=str(directory/'admin'))
        result = subprocess.run([sys.executable,'-c',script],cwd=ROOT/'backend',env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_database_and_config_isolation(self):
        import sqlite3
        import mqtt_store
        root_db = mqtt_store.connect()
        mqtt_store.save(root_db, '2026-11-07T10:00:00Z', 'DMR', 'root-only', {})
        root_db.close()
        for slug in ('ir3abc','ir3xyz'):
            self.get('/'+slug+'/api/live')
            directory = self.registry.directory / slug
            db = directory / 'data' / 'events.sqlite3'
            con = sqlite3.connect(db)
            self.assertEqual(con.execute("SELECT count(*) FROM events WHERE action='root-only'").fetchone()[0], 0)
            con.close()
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(directory / 'dashboard.ini')
            self.assertEqual(cfg['deployment']['node_id'], slug)
            self.assertEqual(oct((directory / 'admin' / 'admin.json').stat().st_mode & 0o777), '0o600')
        response = self.get('/ir3abc/api/config')
        self.assertNotIn(PASSWORD, response.get_data(as_text=True))

    def test_mqtt_sibling_traffic_excluded_from_root(self):
        self.assertTrue(accept_event('mmdvm/rootnode/json', {'DMR':{'node_id':'rootnode'}}))
        self.assertFalse(accept_event('mmdvm/ir3abc/json', {'DMR':{}}))
        self.assertFalse(accept_event('agents/ir3xyz/telemetry', {}))
        self.assertFalse(accept_event('mmdvm/else/json', {'DMR':{'node_id':'ir3abc'}}))


    def test_z_real_broker_end_to_end(self):
        import shutil, socket, subprocess, time
        if not shutil.which('mosquitto'):
            self.skipTest('mosquitto not installed')
        import paho.mqtt.client as mqtt
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.close()
        conf = DIRECTORY / 'mosquitto-test.conf'
        conf.write_text('listener '+str(port)+' 127.0.0.1'+chr(10)+'allow_anonymous true'+chr(10)+'persistence false'+chr(10))
        processes, handles = [], []
        publisher = None
        try:
            broker_log = (DIRECTORY/'broker-test.log').open('wb')
            handles.append(broker_log)
            processes.append(subprocess.Popen(['mosquitto','-c',str(conf)],stdout=broker_log,stderr=broker_log))
            for attempt in range(50):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):
                        break
                except OSError:
                    time.sleep(.1)
            else:
                self.fail('Isolated broker did not start')
            logs = []
            databases = []
            for slug in ('rootnode','ir3abc','ir3xyz'):
                directory = DIRECTORY if slug=='rootnode' else self.registry.directory/slug
                settings = dict(host='127.0.0.1',port=port,topic='mmdvm/+/json' if slug=='rootnode' else 'mmdvm/'+slug+'/json',username='',password='',tls=False)
                (directory/'data'/'mqtt-settings.json').write_text(json.dumps(settings))
                env = dict(os.environ,MMDVM_NODE_CONFIG=str(directory/'dashboard.ini'),MMDVM_NODE_DATA=str(directory/'data'),MMDVM_DASHBOARD_STATE_DIR=str(directory/'admin'))
                if slug!='rootnode':
                    env['MMDVM_MULTI_WORKER']=slug
                else:
                    env.pop('MMDVM_MULTI_WORKER',None)
                log_path = directory/'broker-collector.log'
                log = log_path.open('wb')
                handles.append(log)
                logs.append(log_path)
                databases.append(directory/'data'/'events.sqlite3')
                processes.append(subprocess.Popen([sys.executable,'-u',str(ROOT/'backend'/'mqtt_collector.py')],env=env,stdout=log,stderr=log))
            for attempt in range(80):
                if all('MQTT subscription active' in p.read_text(errors='replace') for p in logs):
                    break
                time.sleep(.1)
            else:
                self.fail('Collectors did not subscribe: '+str([p.read_text() for p in logs]))
            publisher=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client()
            publisher.connect('127.0.0.1',port)
            publisher.loop_start()
            for slug in ('rootnode','ir3abc','ir3xyz'):
                event={'DMR':{'node_id':slug,'action':'broker-test','timestamp':'2026-11-07T13:00:00Z'}}
                publisher.publish('mmdvm/'+slug+'/json',json.dumps(event),qos=1).wait_for_publish(5)
            publisher.publish('mmdvm/ir3abc/json',json.dumps({'DMR':{'node_id':'ir3xyz','action':'broker-test'}}),qos=1).wait_for_publish(5)
            import sqlite3
            counts=[]
            for attempt in range(60):
                counts=[]
                for path in databases:
                    connection=sqlite3.connect(path)
                    counts.append(connection.execute('SELECT count(*) FROM events WHERE action=?',('broker-test',)).fetchone()[0])
                    connection.close()
                if counts==[1,1,1]:
                    break
                time.sleep(.1)
            self.assertEqual(counts,[1,1,1])

            # Exercise supervision without an HTTP request and remove orphan collectors.
            processes[-1].terminate()
            processes[-1].wait(timeout=5)
            worker=self.registry.worker('ir3xyz')
            worker.stop()
            worker.testing=False
            self.registry.testing=False
            self.registry.start_all()
            for attempt in range(60):
                children=Path('/proc/'+str(worker.process.pid)+'/task/'+str(worker.process.pid)+'/children')
                child_ids=children.read_text().split() if children.exists() else []
                if child_ids:
                    break
                time.sleep(.1)
            self.assertTrue(child_ids)
            old_collector=int(child_ids[0])
            old_worker=worker.process.pid
            worker.process.kill()
            worker.process.wait(timeout=5)
            for attempt in range(80):
                if worker.process and worker.process.pid!=old_worker and worker.process.poll() is None:
                    break
                time.sleep(.1)
            self.assertNotEqual(worker.process.pid,old_worker)
            old_stat=Path('/proc/'+str(old_collector)+'/stat')
            for attempt in range(30):
                if not old_stat.exists() or old_stat.read_text().split()[2]=='Z':
                    break
                time.sleep(.1)
            self.assertTrue(not old_stat.exists() or old_stat.read_text().split()[2]=='Z')
            ready=False
            for attempt in range(80):
                children=Path('/proc/'+str(worker.process.pid)+'/task/'+str(worker.process.pid)+'/children')
                new_children=children.read_text().split() if children.exists() else []
                log_path=self.registry.directory/'ir3xyz'/'collector.log'
                log_text=log_path.read_text(errors='replace') if log_path.exists() else ''
                if new_children and ('MQTT subscription active (pid='+new_children[0]+')') in log_text:
                    ready=True
                    break
                time.sleep(.1)
            self.assertTrue(ready, log_text)
            restart_event={'DMR':{'node_id':'ir3xyz','action':'restart-test','timestamp':'2026-11-07T13:01:00Z'}}
            publisher.publish('mmdvm/ir3xyz/json',json.dumps(restart_event),qos=1).wait_for_publish(5)
            count=0
            for attempt in range(50):
                connection=sqlite3.connect(databases[-1])
                count=connection.execute('SELECT count(*) FROM events WHERE action=?',('restart-test',)).fetchone()[0]
                connection.close()
                if count:
                    break
                time.sleep(.1)
            self.assertEqual(count,1)

        finally:
            if publisher:
                publisher.disconnect()
                publisher.loop_stop()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for handle in handles:
                handle.close()


    def test_read_api_never_returns_another_nodes_history(self):
        import sqlite3
        databases=[DIRECTORY/'data'/'events.sqlite3']+[self.registry.directory/slug/'data'/'events.sqlite3' for slug in ('ir3abc','ir3xyz')]
        markers=['PRIMARY_ONLY','NODE_A_ONLY','NODE_B_ONLY']
        for path,marker in zip(databases,markers):
            connection=sqlite3.connect(path)
            for action,stamp in [('start','2026-11-07T14:00:00Z'),('end','2026-11-07T14:00:05Z')]:
                payload=dict(slot=2,src_id='999001',src_info=marker,dst_id=91,group='yes',source='rf',duration=5)
                connection.execute('INSERT INTO events(timestamp,mode,action,payload) VALUES(?,?,?,?)',(stamp,'DMR',action,json.dumps(payload)))
            connection.commit()
            connection.close()
        for prefix,expected in zip(('', '/ir3abc','/ir3xyz'),markers):
            response=self.get(prefix+'/api/heard')
            self.assertEqual(response.status_code,200)
            text=response.get_data(as_text=True)
            self.assertIn(expected,text)
            for other in markers:
                if other!=expected:
                    self.assertNotIn(other,text)


    def test_t_delete_restore_permissions_data_and_processes(self):
        data=self.node('IR9DEL')
        response=self.client.post('/api/admin/multi',base_url=self.base,json=data,headers=self.headers)
        self.assertEqual(response.status_code,201,response.get_data(as_text=True))
        directory=self.registry.directory/'ir9del'
        (directory/'data'/'retained.txt').write_text('node-history-retained')
        secret=(directory/'admin'/'session-secret').read_bytes()
        credentials=(directory/'admin'/'admin.json').read_bytes()
        self.assertEqual(self.get('/ir9del/api/config').status_code,200)
        worker=self.registry.worker('ir9del')
        url='/api/admin/multi/ir9del/delete'
        body={'confirm_callsign':'IR9DEL'}
        guest=app.test_client()
        self.assertEqual(guest.post(url,base_url=self.base,json=body).status_code,401)
        self.assertEqual(self.client.post(url,base_url=self.base,json=body,headers={'Origin':self.base}).status_code,403)
        self.assertEqual(self.client.post(url,base_url=self.base,json=body,headers={**self.headers,'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.post(url,base_url=self.base,json={'confirm_callsign':'IR3ABC'},headers=self.headers).status_code,400)
        response=self.client.post(url,base_url=self.base,json=body,headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        archive=response.get_json()['deleted']['archive_id']
        self.assertFalse(directory.exists())
        archived=self.registry.directory/'.trash'/archive
        self.assertEqual((archived/'data'/'retained.txt').read_text(),'node-history-retained')
        self.assertEqual((archived/'admin'/'session-secret').read_bytes(),secret)
        self.assertTrue(worker.disabled)
        self.assertIsNone(worker.process)
        worker.start()
        self.assertIsNone(worker.process)
        self.assertEqual(self.get('/ir9del/').status_code,404)
        self.assertNotIn('IR9DEL',self.get('/api/multi/nodes').get_data(as_text=True))
        self.assertEqual(self.get('/ir3abc/api/config').status_code,200)
        self.assertEqual(self.get('/api/config').status_code,200)
        management=self.get('/api/admin/multi').get_json()
        self.assertIn(archive,[n['archive_id'] for n in management['deleted']])
        from multi import Registry
        reloaded=Registry(self.registry.directory,testing=True)
        self.assertIn(archive,[n['archive_id'] for n in reloaded.deleted()])
        self.assertNotIn('ir9del',[n['slug'] for n in reloaded.nodes])
        reloaded.close()
        response=self.client.post('/api/admin/multi/restore/'+archive,base_url=self.base,json={},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        self.assertEqual((directory/'admin'/'admin.json').read_bytes(),credentials)
        self.assertEqual((directory/'data'/'retained.txt').read_text(),'node-history-retained')
        self.assertEqual(self.get('/ir9del/api/config').status_code,200)
        self.assertEqual(self.client.post(url,base_url=self.base,json=body,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/admin/multi/rootnode/delete',base_url=self.base,json={'confirm_callsign':'ROOTNODE'},headers=self.headers).status_code,404)
        self.assertEqual(self.client.post('/api/admin/multi/restore/invalid',base_url=self.base,json={},headers=self.headers).status_code,409)

    def test_t_restore_conflict_does_not_overwrite_replacement(self):
        data=self.node('IR9DUP')
        created=self.client.post('/api/admin/multi',base_url=self.base,json=data,headers=self.headers)
        self.assertEqual(created.status_code,201)
        url='/api/admin/multi/ir9dup/delete'
        body={'confirm_callsign':'IR9DUP'}
        deleted=self.client.post(url,base_url=self.base,json=body,headers=self.headers).get_json()['deleted']
        replacement=self.client.post('/api/admin/multi',base_url=self.base,json=data,headers=self.headers)
        self.assertEqual(replacement.status_code,201,replacement.get_data(as_text=True))
        marker=self.registry.directory/'ir9dup'/'data'/'new-node.txt'
        marker.write_text('replacement')
        response=self.client.post('/api/admin/multi/restore/'+deleted['archive_id'],base_url=self.base,json={},headers=self.headers)
        self.assertEqual(response.status_code,409)
        self.assertEqual(marker.read_text(),'replacement')
        self.assertEqual(self.client.post(url,base_url=self.base,json=body,headers=self.headers).status_code,200)

    def test_t_pending_archive_is_completed_after_restart(self):
        from multi import Registry,atomic_json
        directory=DIRECTORY/'crash-case'
        registry=Registry(directory,testing=True)
        node=registry.add(self.node('IR9PEN'))
        tombstone=dict(node,archive_id='a'*32,deleted_at='2026-11-07T12:00:00+00:00')
        atomic_json(registry.path,[tombstone])
        registry.close()
        self.assertTrue((directory/'ir9pen').is_dir())
        restarted=Registry(directory,testing=True)
        self.assertFalse(restarted.nodes)
        self.assertFalse((directory/'ir9pen').exists())
        self.assertTrue((directory/'.trash'/('a'*32)).is_dir())
        restored=restarted.restore('a'*32)
        self.assertEqual(restored['slug'],'ir9pen')
        restarted.close()

    def test_worker_restarts_and_registry_survives_reload(self):
        from multi import Registry
        persisted = Registry(self.registry.directory, testing=True)
        self.assertEqual([n['slug'] for n in persisted.nodes], ['ir3abc','ir3xyz'])
        persisted.close()
        worker = self.registry.worker('ir3xyz')
        worker.process.terminate()
        worker.process.wait(timeout=5)
        self.assertEqual(self.get('/ir3xyz/api/config').status_code, 200)

if __name__ == '__main__':
    unittest.main()
