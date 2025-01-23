import logging
from binance.um_futures import UMFutures
from binance.error import Error
from django.conf import settings
from general.exceptions import PlaceOrderException, CancelOrderException
from exchange_binance.calc import price_to_precision, quantity_to_precision
from exchange_binance.credentials import binance
from exchange_binance.models import Symbol, CopyTradeAccount
from general.data import DataOrder


logger = logging.getLogger(__name__)


class BinanceTrade():
    def __init__(self, symbol: Symbol, side: str, quantity: float):
        self.client = UMFutures(key=binance.api_key, secret=binance.api_secret)
        self.symbol = symbol
        self.side = side
        self.quantity = quantity_to_precision(symbol, quantity)
        self.working_type = 'MARK_PRICE'
        self.time_in_force = 'GTC'
        self.recv_window = settings.BINANCE_RECV_WINDOW
        self.extra = {'symbol': self.symbol, 'side': self.side}

    def get_side(self) -> str:
        if hasattr(self, 'account'):
            return self.side
        return 'BUY' if self.side == 'SELL' else 'SELL'

    def set_leverage(self, leverage: int) -> dict:
        try:
            result = self.client.change_leverage(
                symbol=self.symbol,
                leverage=leverage,
                recvWindow=self.recv_window
            )
            logger.info(
                f'Set leverage to {result["leverage"]}',
                extra=self.extra
            )
        except Error as e:
            logger.error(
                f'Setting leverage failed. {e.error_message}',
                extra=self.extra
            )
            raise PlaceOrderException(e) from None

    def place_market_order(
        self, quantity: float = None, reduce_only: bool = False
    ) -> DataOrder:
        try:
            params = dict(
                symbol=self.symbol,
                side=self.side,
                quantity=self.quantity,
                type='MARKET',
                workingType=self.working_type,
                recvWindow=self.recv_window
            )
            msg = 'to open position' if not reduce_only else 'to close position'
            if quantity:
                quantity = quantity_to_precision(self.symbol, quantity)
                params['quantity'] = quantity
            if reduce_only:
                params['reduceOnly'] = True
                params['side'] = self.get_side()
                logger.info(
                    f'Closing position quantity={params["quantity"]}',
                    extra=self.extra
                )
            result = self.client.new_order(**params)
            o: DataOrder = DataOrder(**result)
            self.extra.update(id=o.order_id)
            logger.info(
                f'Placed market order {msg} {o.status=} {o.orig_qty=} {o.orig_type=}',
                extra=self.extra
            )
            return o
        except Error as e:
            logger.error(
                f'Failed to place market order {msg}. Quantity={self.quantity} '
                f'{e.error_message}',
                extra=self.extra
            )
            raise PlaceOrderException(e) from None

    def place_limit_order(
        self, price: float, quantity: float = None, reduce_only: bool = False
    ) -> DataOrder:
        try:
            price = price_to_precision(self.symbol, price)
            params = dict(
                symbol=self.symbol,
                side=self.side,
                quantity=self.quantity,
                price=price,
                type='LIMIT',
                timeInForce=self.time_in_force,
                recvWindow=self.recv_window
            )
            msg = 'to open position' if not reduce_only else 'to close position'
            if quantity:
                quantity = quantity_to_precision(self.symbol, quantity)
                params['quantity'] = quantity
            if reduce_only:
                params['reduceOnly'] = True
                params['side'] = self.get_side()
                logger.info(
                    f'Closing position quantity={params["quantity"]}',
                    extra=self.extra
                )
            result = self.client.new_order(**params)
            o: DataOrder = DataOrder(**result)
            self.extra.update(id=o.order_id, side=o.side)
            logger.info(
                f'Placed limit order {msg} {o.status=} {o.orig_qty=} {o.orig_type=}',
                extra=self.extra
            )
            return o
        except Error as e:
            logger.error(
                f'Failed to place limit order {msg} {price=} '
                f'{quantity=}. {e.error_message}',
                extra=self.extra
            )
            raise PlaceOrderException(e) from None

    def place_stop_loss_market_order(self, price: float) -> DataOrder:
        try:
            price = price_to_precision(self.symbol, price)
            side = self.get_side()
            result = self.client.new_order(
                symbol=self.symbol,
                side=side,
                type='STOP_MARKET',
                closePosition=True,
                stopPrice=price,
                workingType=self.working_type,
                recvWindow=self.recv_window
            )
            o: DataOrder = DataOrder(**result)
            self.extra.update(id=o.order_id, side=side)
            logger.info(
                f'Placed stop loss order {o.status=} {o.stop_price=} {o.orig_type=}',
                extra=self.extra
            )
            return o
        except Error as e:
            logger.error(
                f'Failed to place stop loss order {price=}. {e.error_message}',
                extra=self.extra
            )
            raise PlaceOrderException(e) from None

    def place_take_profit_market_order(
        self, price: float, quantity: float = None, reduce_only: bool = False
    ) -> DataOrder:
        try:
            price = price_to_precision(self.symbol, price)
            side = self.get_side()
            params = dict(
                symbol=self.symbol,
                side=side,
                type='TAKE_PROFIT_MARKET',
                closePosition=True,
                stopPrice=price,
                workingType=self.working_type,
                recvWindow=self.recv_window
            )
            if quantity:
                quantity = quantity_to_precision(self.symbol, quantity)
                params['quantity'] = quantity
            if reduce_only:
                params['reduceOnly'] = True
            result = self.client.new_order(**params)
            o: DataOrder = DataOrder(**result)
            self.extra.update(id=o.order_id, side=side)
            logger.info(
                f'Placed take profit order {o.status=} {o.stop_price=} '
                f'{o.orig_qty=} {reduce_only=} {o.orig_type=}',
                extra=self.extra
            )
            return o
        except Error as e:
            logger.error(
                f'Failed to place take profit order {price=} {quantity=} '
                f'{reduce_only=}. {e.error_message}',
                extra=self.extra
            )
            raise PlaceOrderException(e) from None

    def place_trailing_stop_market_order(
            self, callback_rate: float, activation_price: float) -> DataOrder:
        try:
            callback_rate = round(callback_rate, 1)
            activation_price = price_to_precision(self.symbol, activation_price)
            side = self.get_side()
            result = self.client.new_order(
                symbol=self.symbol,
                side=side,
                type='TRAILING_STOP_MARKET',
                quantity=self.quantity,
                callbackRate=callback_rate,
                activationPrice=activation_price,
                workingType=self.working_type,
                recvWindow=self.recv_window
            )
            o: DataOrder = DataOrder(**result)
            self.extra.update(id=o.order_id, side=side)
            logger.info(
                f'Placed trailing stop order {o.price_rate=} {o.activation_price=} '
                f'{o.status=} {o.orig_qty=} {o.orig_type=}',
                extra=self.extra
            )
            return o
        except Error as e:
            logger.error(
                f'Failed to place trailing stop order {callback_rate=} '
                f'{activation_price=}. {e.error_message}',
                extra=self.extra
            )
            raise PlaceOrderException(e) from None


class BinanceOrder():
    def __init__(self, symbol: str) -> None:
        self.client = UMFutures(
            key=binance.api_key,
            secret=binance.api_secret
        )
        self.symbol = symbol
        self.recv_window = settings.BINANCE_RECV_WINDOW
        self.extra = {'symbol': symbol}

    def cancel_all_open_orders(self, symbol: str = '') -> None:
        try:
            if not symbol:
                symbol = self.symbol
            result = self.client.cancel_open_orders(
                symbol=symbol,
                recvWindow=self.recv_window
            )
            if result['code'] == 200:
                logger.info(f'{result["msg"]}', extra=self.extra)
            else:
                logger.error(f'Cancelling orders failed. {result=}', extra=self.extra)
        except Error as e:
            logger.error(e.error_message, extra=self.extra)
            raise CancelOrderException(e) from None

    def cancel_multiple_orders(self, order_ids: list, symbol: str = '') -> None:
        try:
            if not symbol:
                symbol = self.symbol
            result = self.client.cancel_batch_order(
                symbol=symbol,
                orderIdList=order_ids,
                origClientOrderIdList=[],
                recvWindow=self.recv_window
            )
            if result:
                for i in result:
                    if i.get('msg'):
                        logger.warning(f'{i["msg"]}', extra=self.extra)
                    else:
                        self.extra.update(id=i['orderId'])
                        logger.info('Cancelled order', extra=self.extra)
            else:
                logger.error(
                    f'Cancelling orders failed. {result=}',
                    extra=self.extra
                )
        except Error as e:
            logger.error(e.error_message, extra=self.extra)
            raise CancelOrderException(e) from None

    def cancel_order(self, order_id: str, symbol: str = '') -> None:
        try:
            if not symbol:
                symbol = self.symbol
            result = self.client.cancel_order(
                symbol=symbol,
                orderId=order_id,
                recvWindow=self.recv_window
            )
            self.extra.update(id=order_id)
            logger.info(
                f'Order status={result["status"]}',
                extra=self.extra
            )
        except Error as e:
            logger.error(e.error_message, extra=self.extra)
            raise CancelOrderException(e) from None


class BinanceCopyTradeOrder(BinanceOrder):
    def __init__(self, account: CopyTradeAccount, symbol: str) -> None:
        self.client = UMFutures(key=account.api_key, secret=account.api_secret)
        if account.use_proxy:
            self.client.proxies = {'https': account.proxy, 'http': account.proxy}
        self.symbol = symbol
        self.recv_window = settings.BINANCE_RECV_WINDOW
        self.extra = {'account': account.id, 'symbol': symbol}


class BinanceCopyTrade(BinanceTrade):
    def __init__(
        self,
        account: CopyTradeAccount,
        symbol: Symbol,
        side: str,
        quantity: float,
        working_type: str,
        time_in_force: str
    ) -> None:
        self.client = UMFutures(key=account.api_key, secret=account.api_secret)
        if account.use_proxy:
            self.client.proxies = {'https': account.proxy, 'http': account.proxy}
        self.account = account
        self.symbol = symbol
        self.side = side
        self.quantity = quantity_to_precision(symbol, quantity)
        self.working_type = working_type
        self.time_in_force = time_in_force
        self.recv_window = settings.BINANCE_RECV_WINDOW
        self.extra = {'account': account.id, 'symbol': symbol, 'side': side}
