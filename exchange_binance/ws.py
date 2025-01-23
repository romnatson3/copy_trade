import logging
import websocket
from websocket._exceptions import (
    WebSocketConnectionClosedException, WebSocketException, WebSocketPayloadException
)
import json
import ctypes
import threading
import time
import hashlib
import hmac
from urllib.parse import urlencode
from typing import Callable
from binance.um_futures import UMFutures
from exchange_binance.credentials import binance


logger = logging.getLogger(__name__)


class SingletonMeta(type):
    def __new__(mcs, name, bases, attrs):
        attrs['_instances'] = {}
        return super().__new__(mcs, name, bases, attrs)

    def __call__(cls, *args, **kwargs):
        account = kwargs.get('account')
        if account:
            id = account.id
        else:
            id = 0
        if id not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[id] = instance
        return cls._instances[id]


class WebSocketBinance(metaclass=SingletonMeta):
    def __init__(self, *args, **kwargs) -> None:
        trace = kwargs.get('trace', False)
        websocket.enableTrace(trace)
        self.ws = websocket.WebSocket()
        self.testnet = kwargs.get('testnet', False)
        self.debug = kwargs.get('debug', True)
        self.is_run = False
        self.handlers = []
        self.name = self.__class__.__name__
        self.threads: dict = {}
        self.methods_names = ['run_forever']
        self.extra = {'symbol': self.name}

    def _message_handler(self, message: str) -> None | dict:
        try:
            message = json.loads(message)
        except json.decoder.JSONDecodeError:
            logger.error(f'Can not decode message. {message=}', extra=self.extra)
            return
        if 'result' in message and message['result'] is None:
            logger.debug('Empty result', extra=self.extra)
            return
        if 'status' in message and message['status'] != 200:
            logger.error(f'Error message: {message}', extra=self.extra)
            return
        if 'result' in message and 'listenKey' in message['result']:
            self.listen_key = message['result']['listenKey']
            logger.info(f'Received listen key: {self.listen_key}', extra=self.extra)
            return
        if self.debug:
            logger.trace(message, extra=self.extra)
        return message

    def add_handler(self, callback: Callable[[int, dict], None]) -> None:
        self.handlers.append(callback)

    def _connect(self, url: str) -> None:
        self.ws.connect(url)
        logger.info(f'Connected to {url}', extra=self.extra)

    def _get_url(self) -> str:
        if self.testnet:
            url = 'wss://fstream.binancefuture.com/ws'
        else:
            url = 'wss://fstream.binance.com/ws'
        return url

    def init(self):
        url = self._get_url()
        self._connect(url)

    def run_forever(self) -> None:
        while self.is_run:
            try:
                self.init()
                while self.is_run:
                    try:
                        message = self.ws.recv()
                        data = self._message_handler(message)
                        if data:
                            for handler in self.handlers:
                                handler(data)
                    except WebSocketPayloadException as e:
                        logger.error(e, extra=self.extra)
                    except WebSocketException:
                        raise
                    except Exception as e:
                        logger.exception(e, extra=self.extra)
            except WebSocketConnectionClosedException:
                logger.warning('Connection closed', extra=self.extra)
            except WebSocketException as e:
                logger.exception(e, extra=self.extra)
                self.ws.close()
            finally:
                time.sleep(3)
        else:
            self.ws.close()
            logger.info('Stopped', extra=self.extra)

    def launch(self):
        try:
            for method in self.methods_names:
                if hasattr(self, method):
                    target = getattr(self, method)
                    name = f'{method}_{self.name}'
                    thread = threading.Thread(target=target, name=name, daemon=True)
                    thread.start()
                    logger.info(f'Thread {thread} is started', extra=self.extra)
                    self.threads[name] = thread
        except Exception as e:
            logger.exception(e, extra=self.extra)
            raise

    def start(self):
        if self.is_run:
            logger.warning('Already running', extra=self.extra)
            return
        self.is_run = True
        self.launch()

    def stop(self):
        self.is_run = False
        self.ws.close()
        logger.warning('Stopping', extra=self.extra)

    def is_alive(self):
        lives = [i.is_alive() for i in self.threads.values()]
        if not lives:
            return False
        return all(lives)

    def kill(self):
        for thread in self.threads.values():
            if not thread or not thread.is_alive():
                continue
            thread_id = ctypes.c_long(thread.ident)
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                thread_id, ctypes.py_object(SystemExit)
            )
            if res == 0:
                raise ValueError('Nonexistent thread id')
            elif res > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                raise SystemError('PyThreadState_SetAsyncExc failed')
            elif res == 1:
                logger.info(f'Thread {thread} is killed', extra=self.extra)
        self.is_run = False
        self.ws.close()


class WebSocketBinanceUserData(WebSocketBinance):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.methods_names = ['run_forever', 'keepalive']

    def new_listen_key(self):
        if binance.testnet:
            base_url = 'https://testnet.binancefuture.com'
        else:
            base_url = 'https://fapi.binance.com'
        self.client = UMFutures(
            key=binance.api_key,
            secret=binance.api_secret,
            base_url=base_url
        )
        listen_key = self.client.new_listen_key().get('listenKey')
        logger.info(f'Listen key: {listen_key}', extra=self.extra)
        return listen_key

    def keepalive(self):
        count = 0
        while self.is_run:
            count += 1
            if count < 1800:
                time.sleep(1)
                continue
            count = 0
            try:
                self.client.renew_listen_key(self.listen_key)
                logger.info(
                    f'Listen key {self.listen_key} is renewed', extra=self.extra
                )
            except Exception as e:
                logger.exception(e, extra=self.extra)
                self.ws.close()
        else:
            logger.info('Stopped', extra=self.extra)

    def init(self):
        self.listen_key = self.new_listen_key()
        url = self._get_url()
        url = f'{url}/{self.listen_key}'
        self._connect(url)


class WebSocketBinanceMarketPrice(WebSocketBinance):
    def subscribe_all_symbols(self):
        self.ws.send(json.dumps(
            {
                'method': 'SUBSCRIBE',
                'params': ['!markPrice@arr@1s'],
                'id': int(time.time() * 1000)
            }
        ))
        logger.info('Subscribed to all symbols', extra=self.extra)

    def subscribe_symbol(self, symbol: str):
        self.ws.send(json.dumps(
            {
                'method': 'SUBSCRIBE',
                'params': [f'{symbol.lower()}@markPrice@1s'],
                'id': self.id
            }
        ))
        logger.info(f'Subscribed to {symbol}', extra=self.extra)

    def unsubscribe(self):
        self.ws.send(json.dumps(
            {
                'method': 'UNSUBSCRIBE',
                'params': ['!markPrice@arr@1s'],
                'id': int(time.time() * 1000)
            }
        ))
        logger.info('Unsubscribed from all symbols', extra=self.extra)

    def init(self):
        url = self._get_url()
        self._connect(url)
        self.subscribe_all_symbols()


class WebSocketBinanceApi(WebSocketBinance):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # self.methods_names = ['run_forever', 'keepalive', 'position_information_v2']
        self.methods_names = ['run_forever', 'keepalive']

    def _get_url(self) -> str:
        if self.testnet:
            url = 'wss://testnet.binancefuture.com/ws-fapi/v1'
        else:
            url = 'wss://ws-fapi.binance.com/ws-fapi/v1'
        return url

    def _start(self) -> None:
        data = {
            'id': str(int(time.time() * 1000)),
            'method': 'userDataStream.start',
            'params': {
                'apiKey': binance.api_key
            }
        }
        self.ws.send(json.dumps(data))
        logger.info('User data stream started', extra=self.extra)

    def _ping(self) -> None:
        data = {
            'id': str(int(time.time() * 1000)),
            'method': 'userDataStream.ping',
            'params': {
                'listenKey': self.listen_key,
                'apiKey': binance.api_key
            }
        }
        logger.debug('User data stream ping sent', extra=self.extra)
        self.ws.send(json.dumps(data))

    def init(self):
        url = self._get_url()
        self._connect(url)
        self._start()

    def keepalive(self):
        count = 0
        while self.is_run:
            count += 1
            if count < 1800:
                time.sleep(1)
                continue
            count = 0
            try:
                self._ping()
            except Exception as e:
                logger.exception(e, extra=self.extra)
                self.ws.close()

    @staticmethod
    def hashing(query_string):
        return hmac.new(
            binance.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _get_account_status_v2(symbol: str = '') -> dict:
        timestamp = int(time.time() * 1000)
        payload = {
            'apiKey': binance.api_key,
            'symbol': symbol,
            'timestamp': timestamp
        }
        if not symbol:
            payload.pop('symbol')
        signature = WebSocketBinanceApi.hashing(urlencode(payload))
        payload.update(signature=signature)
        return {
            'id': str(timestamp),
            'method': 'v2/account.status',
            'params': payload
        }

    @staticmethod
    def _get_position_information_v2(symbol: str = '') -> dict:
        timestamp = int(time.time() * 1000)
        payload = {
            'apiKey': binance.api_key,
            'symbol': symbol,
            'timestamp': timestamp
        }
        if not symbol:
            payload.pop('symbol')
        signature = WebSocketBinanceApi.hashing(urlencode(payload))
        payload.update(signature=signature)
        return {
            'id': str(timestamp),
            'method': 'account.position',
            # 'method': 'v2/account.position',
            'params': payload
        }

    def position_information_v2(self):
        while self.is_run:
            if not self.ws.connected:
                time.sleep(1)
                continue
            data = self._get_position_information_v2()
            self.ws.send(json.dumps(data))
            time.sleep(0.5)
