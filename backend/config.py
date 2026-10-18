from configparser import ConfigParser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "dashboard.ini"

config = ConfigParser(interpolation=None)
config.read(CONFIG_FILE, encoding="utf-8")


def reload_config():
    """Ricarica dashboard.ini senza riavviare il backend."""
    updated = ConfigParser(interpolation=None)
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        updated.read_file(f)
    global config
    config = updated


def get(section, option, fallback=""):
    return config.get(section, option, fallback=fallback)


def getboolean(section, option, fallback=False):
    return config.getboolean(section, option, fallback=fallback)


def get_path(option, fallback=""):
    return get("paths", option, fallback)


def get_mmdvm_ini():
    directory = get_path("mmdvm_dir")
    filename = get_path("mmdvm_file")
    return str(Path(directory) / filename)


def get_tg_list():
    directory = get_path("tg_list_dir")
    filename = get_path("tg_list_file")
    return str(Path(directory) / filename)
