"""Normalizzazione comune dei parametri radio MMDVM."""

from decimal import Decimal, InvalidOperation


def frequency_mhz(value):
    """Converte una frequenza MMDVM da Hz a MHz."""
    try:
        hz = Decimal(str(value).strip())
        if not hz.is_finite() or hz <= 0:
            return ""
        return f"{hz / Decimal(1000000):.4f}"
    except (InvalidOperation, ValueError, TypeError):
        return ""


def calculate_shift(rx_hz, tx_hz):
    """Calcola RX - TX e restituisce lo SHIFT con segno."""
    try:
        rx = Decimal(str(rx_hz).strip())
        tx = Decimal(str(tx_hz).strip())
        if not rx.is_finite() or not tx.is_finite():
            return ""
        if rx <= 0 or tx <= 0:
            return ""
        shift = (rx - tx) / Decimal(1000000)
        return f"{shift:+.3f} MHz"
    except (InvalidOperation, ValueError, TypeError):
        return ""


def fm_ctcss(fm_fields, fm_enabled):
    """Restituisce il CTCSS soltanto quando FM è abilitato."""
    if not fm_enabled:
        return ""

    value = fm_fields.get("CTCSSFrequency", "")
    try:
        frequency = Decimal(str(value).strip())
        if not frequency.is_finite() or frequency <= 0:
            return ""
        return f"{frequency.normalize()} Hz"
    except (InvalidOperation, ValueError, TypeError):
        return ""


def normalize_radio(fields, modes):
    """Normalizza i parametri MMDVM locali o ricevuti via MQTT."""
    info = fields.get("Info", {})
    fm = fields.get("FM", {})
    dmr = fields.get("DMR", {})

    fm_enabled = modes.get("FM") is True
    dmr_enabled = modes.get("DMR") is True

    return {
        "tx_frequency": frequency_mhz(info.get("TXFrequency")),
        "rx_frequency": frequency_mhz(info.get("RXFrequency")),
        "shift": calculate_shift(
            info.get("RXFrequency"),
            info.get("TXFrequency")
        ),
        "power": (
            f"{info['Power']} W"
            if str(info.get("Power", "")).strip()
            else ""
        ),
        "ctcss": fm_ctcss(fm, fm_enabled),
        "dmr_color_code": (
            str(dmr.get("ColorCode", ""))
            if dmr_enabled else ""
        ),
    }
