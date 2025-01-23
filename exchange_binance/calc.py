from exchange_binance.models import Symbol, MainSettings, MasterAccount, CopyTradeAccount
from decimal import Decimal, ROUND_DOWN


def get_quantity_from_usdt(symbol: Symbol, usdt: float) -> float:
    quantity = (usdt * symbol.leverage) / symbol.market_price
    return round(quantity, symbol.data['quantityPrecision'])


# def price_to_precision(symbol: Symbol, price: float) -> str:
#     precision = symbol.data['pricePrecision']
#     price_str = f'{price:.{precision}f}'
#     if '.' in price_str:
#         return price_str.rstrip('0').rstrip('.')
#     return price_str


def price_to_precision(symbol: Symbol, price: float) -> str:
    tick_size = symbol.data['filters'][0]['tickSize'].rstrip('0').rstrip('.')
    price_str = str(
        Decimal(price).quantize(Decimal(tick_size), rounding=ROUND_DOWN)
    )
    return price_str.rstrip('0').rstrip('.')


def quantity_to_precision(symbol: Symbol, quantity: float) -> str:
    precision = symbol.data['quantityPrecision']
    quantity_str = f'{quantity:.{precision}f}'
    if '.' in quantity_str:
        return quantity_str.rstrip('0').rstrip('.')
    return quantity_str
