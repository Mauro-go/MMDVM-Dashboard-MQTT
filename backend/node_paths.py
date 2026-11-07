"""Per-node paths; unset variables preserve the original installation."""
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

def data_file(name):
    return Path(os.environ.get('MMDVM_NODE_DATA', str(BASE_DIR / 'data'))) / name
