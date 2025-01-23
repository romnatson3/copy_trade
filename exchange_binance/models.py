from django.db import models
from django.core.cache import cache


class BaseModel(models.Model):
    class Meta:
        abstract = True

    created_at = models.DateTimeField('created_at', auto_now_add=True)
    updated_at = models.DateTimeField('updated_at', auto_now=True)


class Symbol(BaseModel):
    class Meta:
        verbose_name = 'Symbol'
        verbose_name_plural = 'Symbols'

    symbol = models.CharField(primary_key=True, unique=True, max_length=20)
    data = models.JSONField('Instrument data', default=dict)
    is_active = models.BooleanField('Is active', default=True)
    leverage = models.IntegerField('Leverage', default=20)

    def __str__(self):
        return str(self.symbol)

    @property
    def market_price(self) -> float:
        market_price = cache.get(f'market_price_{self.symbol}')
        return float(market_price) if market_price else 0.0

    def get_last_open_position(self):
        return self.positions.filter(is_open=True).last()


class MainSettings(BaseModel):
    class Meta:
        verbose_name = 'Main settings'
        verbose_name_plural = 'Main settings'

    class SignalSource(models.TextChoices):
        rsi = 'RSI', 'RSI'
        telegram = 'TLG', 'TLG'

    take_profit_rate = models.FloatField('Take profit percent', default=0.0)
    stop_loss_rate = models.FloatField('Stop loss percent', default=0.0)
    trailing_stop_callback_rate = models.FloatField('Trailing stop price rate', default=0.0)
    trailing_stop_activation_price_rate = models.FloatField('Trailing stop activation price rate', default=0.0)
    short_position_limit = models.IntegerField('Short position limit', default=0)
    long_position_limit = models.IntegerField('Long position limit', default=0)
    bull_mode = models.BooleanField('Bull mode', default=False)
    bear_mode = models.BooleanField('Bear mode', default=False)
    signal_source_name = models.CharField('Signal source', choices=SignalSource.choices, default=SignalSource.rsi)
    amount_usdt = models.FloatField('Amount in USDT', default=0.0)
    coefficient = models.FloatField('Coefficient', default=1.0)

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass


class PositionSettingsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('position')


class PositionSettings(BaseModel):
    class Meta:
        verbose_name = 'Position settings'
        verbose_name_plural = 'Position settings'

    objects = PositionSettingsManager()

    position = models.OneToOneField('Position', on_delete=models.CASCADE, related_name='settings')
    take_profit_rate = models.FloatField('Take profit percent', default=0.0)
    stop_loss_rate = models.FloatField('Stop loss percent', default=0.0)
    trailing_stop_callback_rate = models.FloatField('Trailing stop price rate', default=0.0)
    trailing_stop_activation_price_rate = models.FloatField('Trailing stop activation price rate', default=0.0)


class MasterAccount(BaseModel):
    class Meta:
        verbose_name = 'Master account'
        verbose_name_plural = 'Master accounts'

    name = models.CharField('Account name', max_length=100)
    testnet = models.BooleanField('Testnet', default=False)
    api_key = models.CharField('API key', max_length=100, blank=True)
    api_secret = models.CharField('API secret', max_length=100, blank=True)
    wallet_balance = models.FloatField('Wallet balance', default=0.0)
    available_balance = models.FloatField('Available balance', default=0.0)
    margin_balance = models.FloatField('Margin balance', default=0.0)
    cross_unrealized_pnl = models.FloatField('Cross unrealized PNL', default=0.0)
    unrealized_profit = models.FloatField('Unrealized PNL', default=0.0)

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    @property
    def is_master(self):
        return True

    def __str__(self):
        return str(self.name)


class CopyTradeAccount(BaseModel):
    class Meta:
        verbose_name = 'Copy trade account'
        verbose_name_plural = 'Copy trade accounts'

    name = models.CharField('Account name', max_length=100)
    api_key = models.CharField('API key', max_length=100, unique=True)
    api_secret = models.CharField('API secret', max_length=100, unique=True)
    proxy = models.CharField('Proxy', max_length=100, null=True, blank=True)
    use_proxy = models.BooleanField('Use proxy', default=False)
    wallet_balance = models.FloatField('Wallet balance', default=0.0)
    available_balance = models.FloatField('Available balance', default=0.0)
    margin_balance = models.FloatField('Margin balance', default=0.0)
    cross_unrealized_pnl = models.FloatField('Cross unrealized PNL', default=0.0)
    unrealized_profit = models.FloatField('Unrealized PNL', default=0.0)

    @property
    def is_master(self):
        return False

    def __str__(self):
        return f'{self.id} - {self.name}'


class PositionManager(models.Manager):
    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related('symbol', 'settings')
            .prefetch_related('orders')
        )


class Position(BaseModel):
    class Meta:
        verbose_name = 'Position'
        verbose_name_plural = 'Positions'

    objects = PositionManager()

    symbol = models.ForeignKey(
        Symbol, on_delete=models.CASCADE, related_name='positions', help_text='s, symbol')
    position_side = models.CharField('Position side', max_length=10, help_text='ps, positionSide')
    side = models.CharField('Side', max_length=10)
    position_amt = models.FloatField('Position amount', help_text='pa, positionAmt')
    entry_price = models.FloatField('Entry price', help_text='ep, entryPrice')
    break_even_price = models.FloatField('Breakeven price', help_text='bep, breakEvenPrice')
    unrealized_profit = models.FloatField('Unrealized profit', help_text='up, unRealizedProfit, unrealizedProfit')
    acummulated_realized = models.FloatField('Accumulated realized profit', help_text='cr, (Pre-fee) Accumulated Realized', null=True)
    notional = models.FloatField('Notional USDT', help_text='notional', null=True)
    mark_price = models.FloatField('Mark price', help_text='markPrice', null=True)
    update_time = models.BigIntegerField('Update time', help_text='updateTime', null=True)
    liquidation_price = models.FloatField('Liquidation price', help_text='liquidationPrice', null=True)
    is_open = models.BooleanField('Is open', default=True)
    transaction_time = models.BigIntegerField('Transaction time', help_text='transaction time', null=True)

    @property
    def quantity(self):
        return abs(self.position_amt)

    def get_take_profit_price(self, rate: float) -> float:
        if self.side == 'BUY':
            return self.entry_price * (1 + rate / self.symbol.leverage / 100)
        elif self.side == 'SELL':
            return self.entry_price * (1 - rate / self.symbol.leverage / 100)

    def get_stop_loss_price(self, rate: float) -> float:
        if self.side == 'BUY':
            return self.entry_price * (1 - rate / self.symbol.leverage / 100)
        elif self.side == 'SELL':
            return self.entry_price * (1 + rate / self.symbol.leverage / 100)

    def get_trailing_stop_activation_price(self, rate: float) -> float:
        if self.side == 'BUY':
            return self.entry_price * (1 + rate / 100)
        elif self.side == 'SELL':
            return self.entry_price * (1 - rate / 100)

    def get_quantity_by_rate(self, rate: float) -> float:
        return self.quantity * rate / 100

    def get_limit_order_price(self, rate: float) -> float:
        if self.side == 'BUY':
            return self.entry_price * (1 + rate / 100)
        elif self.side == 'SELL':
            return self.entry_price * (1 - rate / 100)

    def get_increased_quantity(self, multiplier: int) -> float:
        return self.quantity * multiplier

    def update(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()

    def __str__(self):
        return f'{self.id} - {self.position_side}'


class OrderManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('symbol', 'position')


class AbstractOrder(models.Model):
    class Meta:
        abstract = True

    order_id = models.BigIntegerField('Order Id', primary_key=True, help_text='i, orderId')
    client_order_id = models.CharField('Client order ID', max_length=50, help_text='c, clientOrderId')
    status = models.CharField('Order status', max_length=50, help_text='X, status')
    side = models.CharField('Side', max_length=10, help_text='S, side. BUY or SELL')
    position_side = models.CharField(
        'Position side', max_length=10, help_text='ps, positionSide. LONG, SHORT, BOTH')
    order_type = models.CharField(
        'Order type', max_length=20, help_text='o, type. MARKET, LIMIT, STOP_MARKET, TRAILING_STOP_MARKET etc.')
    orig_qty = models.FloatField('Original quantity', help_text='q, origQty')
    avg_price = models.FloatField('Average price', help_text='ap, avgPrice', null=True, blank=True)
    working_type = models.CharField(
        'Stop price working type', max_length=20, help_text='wt, workingType', null=True)
    stop_price = models.FloatField('Stop price', help_text='sp, stopPrice', null=True)
    time = models.BigIntegerField('Order trade time', help_text='T, time')
    time_in_force = models.CharField(
        'Time in force', max_length=10, help_text='f, timeInForce. GTC, IOC, FOK, GTX', null=True, blank=True)
    close_position = models.BooleanField('Close position', help_text='cp, closePosition. If close all', null=True)
    reduce_only = models.BooleanField('Reduce only', help_text='R, reduceOnly', null=True)
    activation_price = models.FloatField('Activation price', help_text='AP, activatePrice', null=True, blank=True)
    price_rate = models.FloatField('Callback rate', help_text='cr, priceRate', null=True, blank=True)
    price = models.FloatField('Original price', help_text='p, price', null=True, blank=True)
    orig_type = models.CharField('Original order type', max_length=20, help_text='ot, origType', null=True)
    realized_profit = models.FloatField('Realized profit', help_text='rp', null=True)

    execution_type = models.CharField('Execution type', max_length=10, help_text='x', null=True, blank=True)
    last_filled_qty = models.FloatField('Last filled quantity', help_text='l', null=True, blank=True)
    filled_accum_qty = models.FloatField('Filled accumulated quantity', help_text='z', null=True, blank=True)
    last_filled_price = models.FloatField('Last filled price', help_text='L', null=True, blank=True)
    commission_asset = models.CharField('Commission asset', max_length=10, help_text='N. USDT', null=True, blank=True)
    commission = models.FloatField('Commission', help_text='n', null=True, blank=True)
    trade_id = models.BigIntegerField('Trade ID', help_text='t', null=True, blank=True)
    bids_notional = models.FloatField('Bids notional', help_text='b', null=True, blank=True)
    ask_notional = models.FloatField('Ask notional', help_text='a', null=True, blank=True)
    is_maker = models.BooleanField('Is maker', help_text='m. Is this trade the maker side?', null=True)

    cum_quote = models.FloatField('Cumulative quote', help_text='cumQuote', null=True, blank=True)
    update_time = models.BigIntegerField('Update time', help_text='updateTime', null=True, blank=True)
    executed_qty = models.FloatField('Executed quantity', help_text='executedQty', null=True, blank=True)
    transaction_time = models.BigIntegerField('Transaction time', help_text='transaction time', null=True)


class Order(AbstractOrder):
    class Meta:
        verbose_name = 'Order'
        verbose_name_plural = 'Orders'
        indexes = [
            models.Index(fields=['client_order_id']),
            models.Index(fields=['time']),
        ]

    objects = OrderManager()

    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='orders', null=True)
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, related_name='orders', help_text='s, symbol')

    def cancel(self):
        from exchange_binance.trade import BinanceOrder
        BinanceOrder(self.symbol).cancel_order(self.order_id)

    def __str__(self):
        return f'{self.order_id} - {self.status} - {self.order_type} - {self.orig_qty}'


class CopyTradeOrder(AbstractOrder):
    class Meta:
        verbose_name = 'Copy trade order'
        verbose_name_plural = 'Copy trade orders'
        indexes = [
            models.Index(fields=['client_order_id']),
            models.Index(fields=['time']),
        ]

    copy_trade_account = models.ForeignKey(CopyTradeAccount, on_delete=models.CASCADE, related_name='copy_trade_orders')
    master_order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='copy_trade_orders', null=True)
    symbol = models.ForeignKey(Symbol, on_delete=models.CASCADE, help_text='s, symbol', related_name='copy_trade_orders')

    def __str__(self):
        return f'{self.order_id} - {self.status} - {self.order_type} - {self.orig_qty}'
