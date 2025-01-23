from dataclasses import dataclass
from types import SimpleNamespace as Namespace


@dataclass
class DataOrder:
    def __init__(self, **kwargs: dict):
        order = Namespace(**kwargs)
        data = {
            'order_id': ['i', 'orderId'],
            'client_order_id': ['c', 'clientOrderId'],
            'symbol': ['s', 'symbol'],
            'status': ['X', 'status'],
            'side': ['S', 'side'],
            'position_side': ['ps', 'positionSide'],
            'order_type': ['o', 'type'],
            'orig_type': ['ot', 'origType'],
            'orig_qty': ['q', 'origQty'],
            'avg_price': ['ap', 'avgPrice'],
            'price': ['p', 'price'],
            'working_type': ['wt', 'workingType'],
            'reduce_only': ['R', 'reduceOnly'],
            'close_position': ['cp', 'closePosition'],
            'stop_price': ['sp', 'stopPrice'],
            'time_in_force': ['f', 'timeInForce'],
            'time': ['T', 'time', 'updateTime'],
            'activation_price': ['AP', 'activatePrice'],
            'price_rate': ['cr', 'priceRate'],
            'realized_profit': ['rp'],
            'last_filled_qty': ['l'],
            'last_filled_price': ['L']
        }
        for name, keys in data.items():
            for key in keys:
                if hasattr(order, key):
                    value = getattr(order, key)
                    if name == 'order_id':
                        value = int(value)
                    elif name == 'orig_qty':
                        value = float(value)
                    elif name == 'avg_price':
                        value = float(value)
                    elif name == 'price':
                        value = float(value)
                    elif name == 'stop_price':
                        value = float(value)
                    elif name == 'activation_price':
                        value = float(value)
                    elif name == 'price_rate':
                        value = float(value)
                    elif name == 'realized_profit':
                        value = float(value)
                    elif name == 'last_filled_qty':
                        value = float(value)
                    elif name == 'last_filled_price':
                        value = float(value)
                    elif name == 'time':
                        value = int(value)
                    setattr(self, name, value)
                    break

    def to_dict(self):
        return self.__dict__.copy()

    def __getattr__(self, item):
        return None


@dataclass
class DataPosition():
    def __init__(self, **kwargs: dict):
        position = Namespace(**kwargs)
        data = {
            'symbol': ['s', 'symbol'],
            'position_side': ['ps', 'positionSide'],
            'position_amt': ['pa', 'positionAmt'],
            'entry_price': ['ep', 'entryPrice'],
            'break_even_price': ['bep', 'breakEvenPrice'],
            'unrealized_profit': ['up', 'unRealizedProfit', 'unrealizedProfit'],
            'acummulated_realized': ['cr'],
            'update_time': ['updateTime'],
            'notional': ['notional'],
            'mark_price': ['markPrice'],
            'liquidation_price': ['liquidationPrice'],
            'leverage': ['leverage']
        }
        for name, keys in data.items():
            for key in keys:
                if hasattr(position, key):
                    value = getattr(position, key)
                    if name == 'position_amt':
                        value = float(value)
                    elif name == 'entry_price':
                        value = float(value)
                    elif name == 'break_even_price':
                        value = float(value)
                    elif name == 'unrealized_profit':
                        value = float(value)
                    elif name == 'acummulated_realized':
                        value = float(value)
                    elif name == 'update_time':
                        value = int(value)
                    elif name == 'notional':
                        value = float(value)
                    elif name == 'mark_price':
                        value = float(value)
                    elif name == 'liquidation_price':
                        value = float(value)
                    elif name == 'leverage':
                        value = int(value)
                    setattr(self, name, value)
                    break

    def to_dict(self):
        return self.__dict__

    def __getattr__(self, item):
        return None
