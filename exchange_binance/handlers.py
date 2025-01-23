import logging
from django.core.cache import cache
from exchange_binance.models import Order, Symbol, Position, CopyTradeAccount
from exchange_binance import tasks
from general.data import DataOrder, DataPosition


logger = logging.getLogger(__name__)


def update_all_market_prices(data: list[dict]) -> None:
    for i in data:
        symbol = i['s']
        price = i['p']
        cache.set(f'market_price_{symbol}', price, timeout=5)
    logger.trace(f'Updated market price for {len(data)} symbols')


def copy_trade(data: dict) -> None:
    if data['e'] == 'ORDER_TRADE_UPDATE':
        accounts = CopyTradeAccount.objects.all()
        for account in accounts:
            tasks.copy_trade_order.delay(account.id, data['o'])
    elif data['e'] == 'ACCOUNT_CONFIG_UPDATE':
        accounts = CopyTradeAccount.objects.all()
        for account in accounts:
            tasks.copy_trade_account.delay(account.id, data['ac'])


def positions(data: dict) -> None:
    if data['e'] != 'ACCOUNT_UPDATE':
        return
    for i in data['a']['P']:
        p: DataPosition = DataPosition(**i)
        p.update_time = data['E']
        p.transaction_time = data['T']
        p.symbol: Symbol = Symbol.objects.get(symbol=p.symbol)
        if p.position_amt != 0:
            p.position_side = 'LONG' if p.position_amt > 0 else 'SHORT'
            p.side = 'BUY' if p.position_side == 'LONG' else 'SELL'
            p.is_open = True
        else:
            p.is_open = False
            p.mark_price = p.symbol.market_price
        position = p.symbol.get_last_open_position()
        if position:
            extra = dict(symbol=p.symbol, side=position.side, id=position.id)
            if p.position_amt == 0:
                position.is_open = False
                position.save()
                logger.warning(
                    f'Closed position in database {p.acummulated_realized=}',
                    extra=extra
                )
        else:
            position = Position.objects.create(**p.to_dict())
            extra = {'symbol': p.symbol, 'side': position.side, 'id': position.id}
            logger.warning(
                f'Created position in database {p.position_amt=} {p.entry_price=}',
                extra=extra
            )
            orders = Order.objects.filter(
                position=None, symbol=p.symbol, transaction_time=p.transaction_time
            )
            for order in orders:
                order.position = position
                order.save(update_fields=['position'])
                logger.info(
                    f'Referenced order {order.order_id} to position in database',
                    extra=extra
                )


def orders(data: dict) -> None:
    if data['e'] != 'ORDER_TRADE_UPDATE':
        return
    o: DataOrder = DataOrder(**data['o'])
    o.transaction_time = data['T']
    extra = {'symbol': o.symbol, 'side': o.side, 'id': o.order_id}
    if Order.objects.filter(order_id=o.order_id).exists():
        Order.objects.filter(order_id=o.order_id).update(**o.to_dict())
        logger.info(
            f'Updated order in database {o.status=} {o.orig_qty=} {o.orig_type=}',
            extra=extra
        )
    else:
        o.symbol = Symbol.objects.get(symbol=o.symbol)
        o.position = o.symbol.get_last_open_position()
        Order.objects.create(**o.to_dict())
        logger.debug(
            f'Created order in database {o.status=} {o.orig_qty=} {o.orig_type=}',
            extra=extra
        )
