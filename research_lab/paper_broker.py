"""Alpaca PAPER endpoint only. No live URL, funding or account-creation API."""
import json
import re
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, build_opener
from supervisor.api import NoRedirect
from .data import finite


class PaperBroker:
    URL = 'https://paper-api.alpaca.markets/v2'
    GET_PATHS = {'account', 'clock', 'positions', 'orders', 'orders:by_client_order_id'}

    def __init__(self, key, secret, symbols, opener=None):
        if not key or not secret or not symbols or len(symbols) > 2:
            raise ValueError('paper_credentials_and_universe_required')
        if any(not re.fullmatch('[A-Z][A-Z0-9.]{0,11}', symbol) for symbol in symbols):
            raise ValueError('invalid_paper_symbol')
        self.key, self.secret, self.symbols = key, secret, set(symbols)
        self.opener = opener or build_opener(NoRedirect()).open

    def request(self, method, path, payload=None, query=None):
        if self.URL != 'https://paper-api.alpaca.markets/v2':
            raise ValueError('paper_url_is_fixed')
        if method == 'GET' and path not in self.GET_PATHS and not (path.startswith('assets/') and path[7:] in self.symbols):
            raise ValueError('paper_endpoint_not_allowed')
        if method != 'GET' and not (method == 'POST' and path == 'orders'):
            raise ValueError('paper_endpoint_not_allowed')
        if method == 'POST':
            if not isinstance(payload, dict) or set(payload) != {'symbol', 'qty', 'side', 'type', 'limit_price', 'time_in_force', 'client_order_id'}:
                raise ValueError('paper_order_fields')
            if payload['symbol'] not in self.symbols or payload['side'] not in {'buy', 'sell'} or payload['type'] != 'limit' or payload['time_in_force'] != 'day':
                raise ValueError('paper_long_limit_only')
            if payload['side'] == 'buy' and finite(payload['qty'], 0.00000001) * finite(payload['limit_price'], 0.00000001) > 20:
                raise ValueError('paper_position_limit')
            if payload['side'] == 'sell':
                owned = next((p for p in self.request('GET', 'positions') if p.get('symbol') == payload['symbol']), None)
                if not owned or finite(owned['qty']) < finite(payload['qty'], 0.00000001):
                    raise ValueError('paper_short_selling_forbidden')
        url = self.URL + '/' + path + ('?' + urlencode(query) if query else '')
        request = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                          method=method, headers={'APCA-API-KEY-ID': self.key, 'APCA-API-SECRET-KEY': self.secret, 'Content-Type': 'application/json'})
        try:
            with self.opener(request, timeout=8) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise ValueError('oversized_paper_response')
            return json.loads(raw)
        except HTTPError as exc:
            if method == 'GET' and path == 'orders:by_client_order_id' and exc.code == 404:
                return None
            raise RuntimeError('paper_http_' + str(exc.code)) from None
        except Exception as exc:
            # A timeout is ambiguous: caller must reconcile this client_order_id.
            raise RuntimeError('paper_request_' + type(exc).__name__) from None

    def buy_limit(self, symbol, quantity, limit_price, client_order_id):
        if symbol not in self.symbols or not re.fullmatch('moussa-paper-[a-z0-9-]{1,32}', client_order_id):
            raise ValueError('invalid_paper_order_identity')
        quantity, limit_price = finite(quantity, 0.00000001), finite(limit_price, 0.00000001)
        if quantity != int(quantity):
            raise ValueError('fractional_limit_order_not_supported')
        if quantity * limit_price > 20:
            raise ValueError('paper_position_limit')
        existing = self.request('GET', 'orders:by_client_order_id', query={'client_order_id': client_order_id})
        if existing:
            if existing.get('symbol') != symbol or existing.get('side') != 'buy' or finite(existing['qty']) != quantity or finite(existing['limit_price']) != limit_price:
                raise ValueError('paper_order_identity_collision')
            return existing
        if self.request('GET', 'clock').get('is_open') is not True:
            raise ValueError('market_closed')
        account = self.request('GET', 'account')
        if account.get('trading_blocked') or finite(account['cash']) < quantity * limit_price or account.get('status') != 'ACTIVE':
            raise ValueError('paper_account_not_ready')
        positions = self.request('GET', 'positions')
        pending = self.request('GET', 'orders', query={'status': 'open', 'limit': 500})
        buys = [o for o in pending if o.get('side') == 'buy']
        if any(o.get('type') != 'limit' or o.get('symbol') not in self.symbols for o in buys):
            raise ValueError('unknown_open_paper_order')
        reserved = sum(max(0, finite(o['qty']) - finite(o.get('filled_qty', 0))) * finite(o['limit_price']) for o in buys)
        if len(positions) + len(buys) >= 2 or any(p.get('symbol') == symbol for p in positions + buys) or sum(abs(finite(p['market_value'])) for p in positions) + reserved + quantity * limit_price > 40:
            raise ValueError('aggregate_paper_exposure_limit')
        asset = self.request('GET', 'assets/' + symbol)
        if asset.get('tradable') is not True or asset.get('class') != 'us_equity' or asset.get('status') != 'active':
            raise ValueError('paper_asset_not_supported')
        if quantity != int(quantity) and asset.get('fractionable') is not True:
            raise ValueError('fractional_paper_order_not_supported')
        return self.request('POST', 'orders', {'symbol': symbol, 'qty': str(quantity), 'side': 'buy', 'type': 'limit',
                                              'limit_price': str(limit_price), 'time_in_force': 'day', 'client_order_id': client_order_id})

    def sell_limit(self, symbol, quantity, limit_price, client_order_id):
        if symbol not in self.symbols or not re.fullmatch('moussa-paper-[a-z0-9-]{1,32}', client_order_id):
            raise ValueError('invalid_paper_order_identity')
        quantity, limit_price = finite(quantity, 0.00000001), finite(limit_price, 0.00000001)
        if quantity != int(quantity):
            raise ValueError('fractional_limit_order_not_supported')
        existing = self.request('GET', 'orders:by_client_order_id', query={'client_order_id': client_order_id})
        if existing:
            if existing.get('symbol') != symbol or existing.get('side') != 'sell' or finite(existing['qty']) != quantity or finite(existing['limit_price']) != limit_price:
                raise ValueError('paper_order_identity_collision')
            return existing
        if self.request('GET', 'clock').get('is_open') is not True:
            raise ValueError('market_closed')
        owned = next((p for p in self.request('GET', 'positions') if p.get('symbol') == symbol), None)
        pending = self.request('GET', 'orders', query={'status': 'open', 'limit': 500})
        reserved = sum(max(0, finite(o['qty']) - finite(o.get('filled_qty', 0))) for o in pending if o.get('symbol') == symbol and o.get('side') == 'sell')
        if not owned or finite(owned['qty']) - reserved < quantity:
            raise ValueError('paper_short_selling_forbidden')
        return self.request('POST', 'orders', {'symbol': symbol, 'qty': str(quantity), 'side': 'sell', 'type': 'limit',
                                              'limit_price': str(limit_price), 'time_in_force': 'day', 'client_order_id': client_order_id})
