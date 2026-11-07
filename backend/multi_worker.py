"""A fresh interpreter per repeater prevents module globals crossing nodes."""
import io
import os
import subprocess
import sys
import time
from pathlib import Path

def serve(connection, node_dir, slug, testing=False):
    node_dir = Path(node_dir)
    os.environ.update(MMDVM_NODE_CONFIG=str(node_dir / 'dashboard.ini'),
                      MMDVM_NODE_DATA=str(node_dir / 'data'),
                      MMDVM_DASHBOARD_STATE_DIR=str(node_dir / 'admin'),
                      MMDVM_MULTI_WORKER=slug)
    from mqtt_store import connect
    connect().close()
    from app import app
    from werkzeug.test import run_wsgi_app
    collector = None
    retry_at = 0
    log = (node_dir / 'collector.log').open('ab', buffering=0)
    try:
        while True:
            if not testing and (collector is None or collector.poll() is not None) and time.monotonic() >= retry_at:
                collector = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('mqtt_collector.py'))], stdout=log, stderr=log)
                retry_at = time.monotonic() + 10
            if not connection.poll(1):
                continue
            try:
                message = connection.recv()
            except EOFError:
                break
            if message is None:
                break
            environ, body = message
            environ.update({'wsgi.input': io.BytesIO(body), 'wsgi.errors': sys.stderr,
                            'wsgi.version': (1, 0), 'wsgi.multithread': False,
                            'wsgi.multiprocess': True, 'wsgi.run_once': False})
            try:
                output, status, headers = run_wsgi_app(app, environ, buffered=True)
                connection.send((status, headers, b''.join(output)))
            except Exception:
                import traceback
                traceback.print_exc(file=sys.stderr)
                connection.send(('500 Internal Server Error', [('Content-Type', 'text/plain')], b'Node request failed'))
    finally:
        if collector is not None and collector.poll() is None:
            collector.terminate()
            try:
                collector.wait(timeout=5)
            except subprocess.TimeoutExpired:
                collector.kill()
                collector.wait()
        log.close()
        connection.close()

if __name__ == '__main__':
    from multiprocessing.connection import Connection
    serve(Connection(int(sys.argv[1])), sys.argv[2], sys.argv[3], sys.argv[4] == 'test')
