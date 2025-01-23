import logging
import threading
import time
import random
from types import SimpleNamespace as Namespace
from django.conf import settings
from django.core.cache import cache
# from celery.utils.log import get_task_logger
from binance.um_futures import UMFutures
from exchange_binance.models import (
    Symbol, Position, Order, MainSettings, MasterAccount, CopyTradeAccount,
    CopyTradeOrder
)
from copy_trade.celery import app
from general.utils import TaskLock
from exchange_binance.ws import WebSocketBinanceMarketPrice, WebSocketBinanceUserData
from general.exceptions import AcquireLockException, LimitUsageException
from exchange_binance import handlers
from celery.signals import worker_ready
from exchange_binance.trade import (
    BinanceTrade, BinanceOrder, BinanceCopyTrade, BinanceCopyTradeOrder
)
from exchange_binance import calc
from exchange_binance.credentials import binance
from general.data import DataOrder, DataPosition


# logger = get_task_logger(__name__)
logger = logging.getLogger(__name__)


@app.task
def update_symbols() -> None:
    try:
        client = UMFutures(key=binance.api_key, secret=binance.api_secret)
        result = client.exchange_info()
        brackets = client.leverage_brackets()
        brackets = {i['symbol']: i['brackets'] for i in brackets}
        symbols = result['symbols']
        for i in symbols:
            symbol = i['symbol']
            max_leverage = brackets[symbol][0]['initialLeverage']
            if max_leverage > settings.BINANCE_LEVERAGE:
                leverage = max_leverage
            else:
                leverage = settings.BINANCE_LEVERAGE
            try:
                symbol = Symbol.objects.get(symbol=symbol)
                symbol.data = i
                # symbol.is_active = i['status'] == 'TRADING'
                symbol.save(update_fields=['data', 'is_active'])
                logger.debug(f'Updated binance symbol {symbol}')
            except Symbol.DoesNotExist:
                symbol = Symbol.objects.create(
                    symbol=symbol,
                    data=i,
                    leverage=leverage,
                    is_active=i['status'] == 'TRADING'
                )
                logger.info(f'Created binance symbol {symbol}')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def get_limit_usage() -> None:
    try:
        with TaskLock('task_get_limit_usage'):
            client = UMFutures(show_limit_usage=True)
            result = client.time()
            used_weight = int(result['limit_usage']['x-mbx-used-weight-1m'])
            logger.trace(f'Limit usage: {used_weight}')
            if used_weight > settings.BINANCE_LIMIT_USAGE:
                logger.warning(f'Limit usage is too high: {used_weight}')
                cache.set('limit_usage_too_high', True, timeout=60)
            else:
                cache.delete('limit_usage_too_high')
    except AcquireLockException:
        logger.trace('Task get limit usage is now running')
    except Exception as e:
        logger.exception(e)
        raise e


def update_account_balances(account) -> None:
    extra = {'account': account.id, 'symbol': account.name}
    try:
        client = UMFutures(key=account.api_key, secret=account.api_secret)
        result = client.sign_request('GET', url_path='/fapi/v3/account')
        data: dict = next((i for i in result['assets'] if i.get('asset') == 'USDT'))
        account.wallet_balance = float(data['walletBalance'])
        account.margin_balance = float(data['marginBalance'])
        account.available_balance = float(data['availableBalance'])
        account.cross_unrealized_pnl = float(data['crossUnPnl'])
        account.unrealized_profit = float(data['unrealizedProfit'])
        account.save()
        logger.trace(
            f'Updated balances: wallet_balance={account.wallet_balance:.2f} '
            f'margin_balance={account.margin_balance:.2f} '
            f'available_balance={account.available_balance:.2f} '
            f'cross_unrealized_pnl={account.cross_unrealized_pnl:.2f} '
            f'unrealized_profit={account.unrealized_profit:.2f}',
            extra=extra
        )
    except Exception as e:
        logger.exception(e, extra=extra)


@app.task
def update_balances():
    try:
        with TaskLock('task_update_balances', use_limit_usage=True):
            master_account = MasterAccount.objects.first()
            update_account_balances(master_account)
            copy_trade_accounts = CopyTradeAccount.objects.all()
            for account in copy_trade_accounts:
                threading.Thread(target=update_account_balances, args=(account,)).start()
    except LimitUsageException:
        logger.warning('Update balances limit usage is too high. Task is skipped')
    except AcquireLockException:
        logger.trace('Task update balances is now running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def update_positions() -> None:
    try:
        with TaskLock('task_update_positions', use_limit_usage=True):
            client = UMFutures(key=binance.api_key, secret=binance.api_secret)
            positions = client.sign_request('GET', url_path='/fapi/v3/positionRisk')
            if not positions:
                logger.trace('No open positions found')
                return
            for i in positions:
                p: DataPosition = DataPosition(**i)
                p.position_side = 'LONG' if p.position_amt > 0 else 'SHORT'
                p.side = 'BUY' if p.position_side == 'LONG' else 'SELL'
                p.symbol: Symbol = Symbol.objects.filter(symbol=p.symbol).first()
                if not p.symbol:
                    logger.warning(f'Symbol {p.symbol} not found in database')
                    continue
                extra = dict(symbol=p.symbol, side=p.side)
                position: Position = p.symbol.get_last_open_position()
                if position:
                    Position.objects.filter(id=position.id).update(**p.to_dict())
                    extra.update(id=position.id)
                    logger.trace(
                        f'Updated position in database {p.position_amt=} '
                        f'{p.entry_price=:.5f} {p.notional=:.2f} '
                        f'{p.unrealized_profit=:.5f}',
                        extra=extra
                    )
                else:
                    logger.critical(
                        'Found position in binance, but not in database '
                        f'{p.position_amt=} {p.entry_price=:.5f} {p.notional=:.2f} '
                        f'{p.unrealized_profit=:.5f}',
                        extra=extra
                    )
                    # position = Position.objects.create(**p.to_dict())
                    # extra.update(id=position.id)
                    # logger.warning(
                    #     f'Created position in database {p.position_amt=} '
                    #     f'{p.entry_price=} {p.notional=}',
                    #     extra=extra
                    # )
    except LimitUsageException:
        logger.warning('Update positions limit usage is too high. Task is skipped')
    except AcquireLockException:
        logger.trace('Task update positions is now running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def update_open_orders() -> None:
    try:
        with TaskLock('task_update_open_orders', use_limit_usage=True):
            client = UMFutures(key=binance.api_key, secret=binance.api_secret)
            result = client.get_orders()
            if not result:
                logger.trace('No open orders found')
                return
            for i in result:
                o: DataOrder = DataOrder(**i)
                o.symbol: Symbol = Symbol.objects.get(symbol=o.symbol)
                position: Position = o.symbol.get_last_open_position()
                if position:
                    o.position = position
                extra = {'symbol': o.symbol, 'side': o.side, 'id': o.order_id}
                if Order.objects.filter(order_id=o.order_id).exists():
                    Order.objects.filter(order_id=o.order_id).update(**o.to_dict())
                    logger.debug(
                        f'Updated order in database {o.status=} {o.orig_qty=} {o.orig_type=}',
                        extra=extra
                    )
                else:
                    Order.objects.create(**o.to_dict())
                    logger.debug(
                        f'Created order in database {o.status=} {o.orig_qty=} {o.orig_type=}',
                        extra=extra
                    )
    except LimitUsageException:
        logger.warning('Update open orders limit usage is too high. Task is skipped')
    except AcquireLockException:
        logger.trace('Task update open orders is now running')
    except Exception as e:
        logger.exception(e)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    update_open_orders.apply_async()


@app.task
def run_websocket_binance_market_price() -> None:
    try:
        with TaskLock('task_run_websocket_binance_market_price'):
            ws = WebSocketBinanceMarketPrice(testnet=binance.testnet, debug=False)
            if ws.is_alive():
                logger.debug('Alive and running', extra={'symbol': ws.name})
            else:
                ws.kill()
                ws.start()
                ws.add_handler(handlers.update_all_market_prices)
    except AcquireLockException:
        logger.trace('Task run_binance_market_price is currently running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def run_websocket_binance_user_data() -> None:
    try:
        with TaskLock('task_run_websocket_binance_user_data'):
            ws = WebSocketBinanceUserData()
            global credentials
            if 'credentials' in globals():
                if (
                    credentials.get('api_key') != binance.api_key or
                    credentials.get('api_secret') != binance.api_secret
                ):
                    logger.warning('Master account credentials changed. Restarting websocket')
                    credentials = dict(
                        api_key=binance.api_key, api_secret=binance.api_secret
                    )
                    ws.stop()
                    time.sleep(5)
            else:
                logger.info('First run of binance user data websocket')
                credentials = dict(
                    api_key=binance.api_key, api_secret=binance.api_secret
                )
            if ws.is_alive():
                logger.debug('Alive and running', extra={'symbol': ws.name})
            else:
                ws.kill()
                ws.start()
                ws.add_handler(handlers.orders)
                ws.add_handler(handlers.positions)
                ws.add_handler(handlers.copy_trade)
    except AcquireLockException:
        logger.trace('Task run_websocket_binance_user_data is currently running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def cancel_all_open_orders(symbol: str) -> None:
    try:
        with TaskLock(f'task_cancel_all_open_orders_{symbol}'):
            BinanceOrder(symbol).cancel_all_open_orders()
    except AcquireLockException:
        logger.trace('Task cancel all open orders is now running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def placing_orders_after_opening_position(position_id: int) -> None:
    try:
        with TaskLock(f'placing_orders_after_opening_position_{position_id}'):
            position = Position.objects.get(id=position_id)
            settings = position.settings
            trade = BinanceTrade(
                symbol=position.symbol,
                side=position.side,
                quantity=position.quantity
            )
            if settings.take_profit_rate:
                price = position.get_take_profit_price(settings.take_profit_rate)
                trade.place_take_profit_market_order(price)
            if settings.stop_loss_rate:
                price = position.get_stop_loss_price(settings.stop_loss_rate)
                trade.place_stop_loss_market_order(price)
            if (
                settings.trailing_stop_callback_rate and
                settings.trailing_stop_activation_price_rate
            ):
                activation_price = position.get_trailing_stop_activation_price(
                    settings.trailing_stop_activation_price_rate
                )
                trade.place_trailing_stop_market_order(
                    settings.trailing_stop_callback_rate, activation_price
                )
    except AcquireLockException:
        logger.trace('Task placing orders after opening position is now running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def copy_trade_account(account_id: int, data: dict) -> None:
    account = CopyTradeAccount.objects.get(id=account_id)
    symbol = data['s']
    leverage = data['l']
    extra = {'account': account.id, 'symbol': symbol}
    try:
        client = UMFutures(key=account.api_key, secret=account.api_secret)
        if account.use_proxy:
            client.proxies = {'https': account.proxy, 'http': account.proxy}
        result = client.change_leverage(
            symbol,
            leverage,
            recvWindow=settings.BINANCE_RECV_WINDOW
        )
        logger.info(f'Set leverage to {result["leverage"]}', extra=extra)
    except Exception as e:
        logger.exception(e, extra=extra)
        raise e


@app.task
def copy_trade_order(account_id: int, data: dict) -> None:
    try:
        master_order: DataOrder = DataOrder(**data)
        account = CopyTradeAccount.objects.get(id=account_id)
        symbol = Symbol.objects.get(symbol=master_order.symbol)
        copy_trade_order: DataOrder = None
        extra = {'account': account.id, 'symbol': symbol}
        coefficient = MainSettings.objects.values_list('coefficient', flat=True).first()
        quantity = round(master_order.orig_qty * coefficient, 3)
        logger.info(
            'Calculating quantity for copy trade: '
            f'{master_order.orig_qty} * {coefficient} = {quantity}',
            extra=extra
        )
        trade = BinanceCopyTrade(
            account=account,
            symbol=symbol,
            side=master_order.side,
            quantity=quantity,
            working_type=master_order.working_type,
            time_in_force=master_order.time_in_force,
        )
        if master_order.status == 'NEW':
            if master_order.order_type == 'MARKET':
                copy_trade_order = trade.place_market_order(
                    reduce_only=master_order.reduce_only
                )
            elif master_order.order_type == 'LIMIT':
                copy_trade_order = trade.place_limit_order(
                    master_order.price, reduce_only=master_order.reduce_only
                )
            elif master_order.order_type == 'TAKE_PROFIT_MARKET':
                copy_trade_order = trade.place_take_profit_market_order(
                    master_order.stop_price
                )
            elif master_order.order_type == 'STOP_MARKET':
                copy_trade_order = trade.place_stop_loss_market_order(
                    master_order.stop_price
                )
            elif master_order.order_type == 'TRAILING_STOP_MARKET':
                copy_trade_order = trade.place_trailing_stop_market_order(
                    master_order.price_rate,
                    master_order.activation_price
                )
        elif master_order.status == 'CANCELED':
            try:
                order = CopyTradeOrder.objects.get(
                    master_order_id=master_order.order_id)
                BinanceCopyTradeOrder(
                    account, symbol.symbol).cancel_order(order.order_id)
                extra.update(side=order.side, id=order.order_id)
                logger.warning(
                    f'Canceled order, related to {master_order.order_id=}',
                    extra=extra
                )
            except CopyTradeOrder.DoesNotExist:
                logger.critical(
                    f'Not found copy trade order for {master_order.order_id=}',
                    extra=extra
                )
        elif master_order.status == 'FILLED':
            ...
        elif master_order.status == 'EXPIRED':
            ...
        if copy_trade_order:
            copy_trade_order.symbol = symbol
            copy_trade_order.master_order_id = master_order.order_id
            copy_trade_order.copy_trade_account = account
            defaults = copy_trade_order.to_dict()
            defaults.pop('order_id')
            extra.update(side=copy_trade_order.side, id=copy_trade_order.order_id)
            o, created = CopyTradeOrder.objects.update_or_create(
                order_id=copy_trade_order.order_id,
                defaults=defaults
            )
            if created:
                logger.debug(
                    f'Created order in database {o.status=} {o.orig_qty=} {o.orig_type=}',
                    extra=extra
                )
            else:
                logger.debug(
                    f'Updated order in database {o.status=} {o.orig_qty=} {o.orig_type=}',
                    extra=extra
                )
    except Exception as e:
        logger.exception(e)
        raise e


@app.task
def place_market_or_limit_order(position_id: int, validated_data: dict) -> dict:
    position = Position.objects.get(id=position_id)
    data = Namespace(**validated_data)
    extra = {'symbol': position.symbol, 'side': position.side, 'id': position.id}
    try:
        trade = BinanceTrade(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity
        )
        if data.order_type == 'MARKET':
            quantity = position.get_quantity_by_rate(data.quantity_rate)
            order = trade.place_market_order(quantity=quantity, reduce_only=True)
            msg = (f'Position closed partially successful. {order.orig_qty=}')
            logger.info(msg, extra=extra)
        elif data.order_type == 'LIMIT':
            price = position.get_limit_order_price(data.price_rate)
            quantity = position.get_quantity_by_rate(data.quantity_rate)
            order = trade.place_limit_order(price, quantity=quantity, reduce_only=True)
            msg = (
                f'Limit order placed successfully. {order.orig_qty=} {order.price=}'
            )
            logger.info(msg, extra=extra)
        error = False
    except Exception as e:
        error = True
        msg = str(e)
        logger.exception(e, extra=extra)
    return {'error': error, 'detail': msg}


@app.task
def increase_position(position_id: int, validated_data: dict) -> dict:
    position = Position.objects.get(id=position_id)
    extra = {'symbol': position.symbol, 'side': position.side, 'id': position.id}
    multiplier = validated_data['multiplier']
    try:
        quantity = position.get_increased_quantity(multiplier)
        trade = BinanceTrade(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity
        )
        order = trade.place_market_order(quantity=quantity)
        msg = f'Increased position successfully. {order.orig_qty=}'
        logger.info(msg, extra=extra)
        error = False
    except Exception as e:
        error = True
        msg = str(e)
        logger.exception(e, extra=extra)
    return {'error': error, 'detail': msg}


@app.task
def replacing_orders(
    position_id: int,
    changed_fields: list[str],
    validated_data: dict
) -> None:
    position = Position.objects.get(id=position_id)
    extra = dict(symbol=position.symbol, id=position.id, side=position.side)
    i = Namespace(**validated_data)
    try:
        trade = BinanceTrade(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity
        )
        if 'take_profit_rate' in changed_fields:
            order = position.orders.filter(
                status__in=['NEW', 'PARTIALLY_FILLED'],
                order_type='TAKE_PROFIT_MARKET'
            ).last()
            if order:
                order.cancel()
                logger.debug('Current take profit order canceled', extra=extra)
            else:
                logger.debug('Current take profit order not found', extra=extra)
            if i.take_profit_rate:
                price = position.get_take_profit_price(i.take_profit_rate)
                trade.place_take_profit_market_order(price)
            else:
                logger.debug('Take profit was disabled', extra=extra)
        if 'stop_loss_rate' in changed_fields:
            order = position.orders.filter(
                status__in=['NEW', 'PARTIALLY_FILLED'],
                order_type='STOP_MARKET'
            ).last()
            if order:
                order.cancel()
                logger.debug('Current stop loss order canceled', extra=extra)
            else:
                logger.debug('Current stop loss order not found', extra=extra)
            if i.stop_loss_rate:
                price = position.get_stop_loss_price(i.stop_loss_rate)
                trade.place_stop_loss_market_order(price)
            else:
                logger.debug('Stop loss was disabled', extra=extra)
        if 'trailing_stop_activation_price_rate' in changed_fields:
            order = position.orders.filter(
                status__in=['NEW', 'PARTIALLY_FILLED'],
                order_type='TRAILING_STOP_MARKET'
            ).last()
            if order:
                order.cancel()
                logger.debug('Current trailing stop order canceled', extra=extra)
            else:
                logger.debug('Current trailing stop order not found', extra=extra)
            if i.trailing_stop_activation_price_rate:
                activation_price = position.get_trailing_stop_activation_price(
                    i.trailing_stop_activation_price_rate
                )
                trade.place_trailing_stop_market_order(
                    validated_data['trailing_stop_callback_rate'], activation_price
                )
            else:
                logger.debug('Trailing stop was disabled', extra=extra)
        logger.info('Updated position settings successfully', extra=extra)
        return {'error': False}
    except Exception as e:
        logger.exception(e, extra=extra)
        return {'error': True, 'detail': str(e)}


@app.task
def close_positions(position_id: int = None, unrealized_profit: bool = None) -> dict:
    if position_id:
        positions = Position.objects.filter(id=position_id)
    else:
        if unrealized_profit:
            positions = Position.objects.filter(
                is_open=True, unrealized_profit__gt=0
            )
            logger.debug(
                f'Found {positions.count()} open profitable positions. Closing all positions'
            )
        else:
            positions = Position.objects.filter(is_open=True)
            logger.debug(
                f'Found {positions.count()} open positions. Closing all positions'
            )
    detail = []
    for position in positions:
        extra = dict(symbol=position.symbol, side=position.side, id=position.id)
        logger.debug('Closing position', extra=extra)
        try:
            trade = BinanceTrade(
                symbol=position.symbol,
                side=position.side,
                quantity=position.quantity
            )
            trade.place_market_order(reduce_only=True)
            logger.warning(
                f'Position closed successfully {position.unrealized_profit=}',
                extra=extra
            )
            detail.append({'position_id': position.id, 'status': 'success'})
        except Exception as e:
            logger.exception(e, extra=extra)
            detail.append(
                {'position_id': position.id, 'status': 'failed', 'detail': str(e)}
            )
    if all(i['status'] == 'success' for i in detail):
        return {'error': False, 'detail': detail}
    return {'error': True, 'detail': detail}


@app.task
def open_position_signal(symbol: str, side: str) -> None:
    try:
        with TaskLock(f'task_open_position_{symbol}'):
            symbol = Symbol.objects.get(symbol=symbol)
            symbol.leverage = settings.BINANCE_LEVERAGE
            symbol.save(update_fields=['leverage'])
            BinanceOrder(symbol).cancel_all_open_orders()
            cache.delete(f'open_position_manually_{symbol}')
            amount_usdt = MainSettings.objects.first().amount_usdt
            quantity = calc.get_quantity_from_usdt(symbol, amount_usdt)
            trade = BinanceTrade(symbol=symbol, side=side, quantity=quantity)
            trade.set_leverage(symbol.leverage)
            trade.place_market_order()
    except AcquireLockException:
        logger.trace('Task open position is now running')
    except Exception as e:
        logger.exception(e)
        raise e


@app.task(bind=True, time_limit=10)
def open_position_manually(self, data: dict) -> dict:
    try:
        i = Namespace(**data)
        extra = {'symbol': i.symbol, 'side': i.side}
        symbol = Symbol.objects.get(symbol=i.symbol)
        symbol.leverage = i.leverage
        symbol.save(update_fields=['leverage'])
        settings: dict = dict(
            take_profit_rate=i.take_profit_rate,
            stop_loss_rate=i.stop_loss_rate,
            trailing_stop_callback_rate=i.trailing_stop_callback_rate,
            trailing_stop_activation_price_rate=i.trailing_stop_activation_price_rate
        )
        cache.set(f'open_position_manually_{symbol}', settings, timeout=None)
        logger.debug('Saved manually settings into cahce', extra=extra)
        quantity = calc.get_quantity_from_usdt(symbol, i.amount_usdt)
        trade = BinanceTrade(symbol=symbol, side=i.side, quantity=quantity)
        trade.set_leverage(i.leverage)
        if i.order_type == 'MARKET':
            o: DataOrder = trade.place_market_order()
        elif i.order_type == 'LIMIT':
            o: DataOrder = trade.place_limit_order(i.price)
        extra.update(id=o.order_id)
        logger.info(
            f'Opened position manually {o.orig_qty=} {o.price=} {o.order_type=}',
            extra=extra
        )
        return {'error': False, 'detail': f'Order {o.order_id} placed successfully'}
    except Exception as e:
        logger.exception(e)
        return {'error': True, 'detail': str(e)}


@app.task
def price_change_percent_strategy(data: dict) -> dict:
    try:
        extra = {'side': data['side']}
        client = UMFutures(key=binance.api_key, secret=binance.api_secret)
        symbol_percent: list[tuple[str, float]] = (
            sorted(
                [
                    (i['symbol'], float(i['priceChangePercent']))
                    for i in client.ticker_24hr_price_change()
                    if i['symbol'].endswith('USDT')
                ],
                key=lambda x: x[1]
            )
        )
        if data['side'] == 'BUY':
            symbol_percent = symbol_percent[:len(symbol_percent) // 2]
        elif data['side'] == 'SELL':
            symbol_percent = symbol_percent[-len(symbol_percent) // 2:]
        symbol_percent = random.sample(symbol_percent, k=data['amount'])
        logger.info(
            f'Found {symbol_percent} symbols for price change percent strategy',
            extra=extra
        )
        symbols = []
        for symbol, _ in symbol_percent:
            extra.update(symbol=symbol)
            if Position.objects.filter(symbol=symbol, is_open=True).exists():
                logger.warning('Position already opened. Skipping', extra=extra)
                continue
            open_position_signal.delay(symbol, data['side'])
            symbols.append(symbol)
        return {'error': False, 'detail': f'Signal to open position sent for {symbols}'}
    except Exception as e:
        logger.exception(e)
        return {'error': True, 'detail': str(e)}
