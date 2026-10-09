"""Dated ECB reference funding. No guessed rate and no conversion order."""
import json
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen
from xml.etree import ElementTree as ET
from .data import finite, stamp
from supervisor.report import atomic_write

URL = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml'


def validate_fx(value, now):
    when = stamp(value['rate_at'])
    if not 0 <= (now-when).total_seconds() <= 96*3600:
        raise ValueError('ecb_rate_unavailable')
    rate = finite(value['usd_per_eur'], .1)
    if rate > 10 or value.get('source') != URL:
        raise ValueError('invalid_ecb_rate')
    return {**value, 'usd_per_eur': rate}


def collect(path, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        previous = json.loads(path.read_text())
        if stamp(previous['collected_at']).date() == now.date():
            return validate_fx(previous, now)
    except (OSError, ValueError, KeyError, TypeError):
        previous = None
    try:
        with urlopen(URL, timeout=12) as response:
            raw = response.read(20000)
        date, rate = None, None
        for element in ET.fromstring(raw).iter():
            if element.get('time'):
                date = element.get('time')
            if element.get('currency') == 'USD':
                rate = element.get('rate')
        # Publication is afternoon European time. This reference is used only
        # after this actual download, never as a historical intraday execution.
        value = {'source': URL, 'date': date, 'usd_per_eur': rate,
                 'rate_at': datetime.fromisoformat(date).replace(tzinfo=timezone.utc).isoformat(),
                 'collected_at': now.isoformat()}
        value = validate_fx(value, now)
        atomic_write(path, json.dumps(value, allow_nan=False))
        return value
    except Exception:
        if previous:
            return validate_fx(previous, now)
        raise
