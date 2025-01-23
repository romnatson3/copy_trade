import logging
import re
from datetime import datetime
from types import SimpleNamespace as Namespace
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth.models import update_last_login
from django.db.models import Count
from exchange_binance.models import (
    Symbol, Position, Order, MainSettings, CopyTradeAccount, PositionSettings,
    MasterAccount
)
from general.exceptions import CustomAPIException


logger = logging.getLogger(__name__)


class DummyStatusSerializer(serializers.Serializer):
    position_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=['success', 'failed'])
    # detail = serializers.CharField(required=False)


class DummyClosePositionsSerializer(serializers.Serializer):
    detail = serializers.ListField(
        child=DummyStatusSerializer()
    )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        refresh = self.get_token(self.user)
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        # Add custom data here
        data['access_token_lifetime'] = str(refresh.access_token.lifetime)
        data['access_token_expiry'] = str(datetime.now() + refresh.access_token.lifetime)
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        return data


class MasterAccountCredentialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterAccount
        fields = ['api_key', 'api_secret']

    def validate(self, data):
        if not data.get('api_key') or not data.get('api_secret'):
            raise CustomAPIException('error', 'API Key and Secret are required')
        return data


class MasterAccountBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterAccount
        fields = [
            'wallet_balance', 'available_balance', 'margin_balance',
            'cross_unrealized_pnl', 'unrealized_profit'
        ]
        read_only_fields = fields


class CopyTradeAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CopyTradeAccount
        fields = [
            'id', 'name', 'api_key', 'api_secret', 'proxy', 'use_proxy'
        ]
        read_only_fields = ['id']

    def validate_proxy(self, value):
        initial_data = self.initial_data
        if initial_data.get('use_proxy'):
            if not value:
                raise serializers.ValidationError('Proxy url is required')
        if value:
            if re.match(r'^https?://.+:.+$', value):
                return value
            raise serializers.ValidationError('Invalid proxy url')
        return value


class PositionSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PositionSettings
        fields = [
            'take_profit_rate', 'stop_loss_rate',
            'trailing_stop_callback_rate', 'trailing_stop_activation_price_rate'
        ]
        extra_kwargs = {
            'take_profit_rate': {'required': True},
            'stop_loss_rate': {'required': True},
            'trailing_stop_callback_rate': {'required': True},
            'trailing_stop_activation_price_rate': {'required': True}
        }

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
            i = Namespace(**data)
            if (
                i.take_profit_rate != 0 and (i.trailing_stop_callback_rate != 0 or
                                             i.trailing_stop_activation_price_rate != 0)
            ):
                raise CustomAPIException(
                    'take_profit_rate',
                    'Take profit rate cannot be set with trailing stop'
                )
            if i.trailing_stop_callback_rate > 0 and i.trailing_stop_activation_price_rate == 0:
                raise CustomAPIException(
                    'trailing_stop_activation_price_rate',
                    'Trailing stop activation price rate is required'
                )
            if i.trailing_stop_callback_rate == 0 and i.trailing_stop_activation_price_rate > 0:
                raise CustomAPIException(
                    'trailing_stop_callback_rate',
                    'Trailing stop price rate is required'
                )
            if i.trailing_stop_callback_rate > 0:
                if i.trailing_stop_callback_rate < 0.1 or i.trailing_stop_callback_rate > 10:
                    raise CustomAPIException(
                        'trailing_stop_callback_rate',
                        'Trailing stop price rate must be between 0.1 and 10'
                    )
            return data
        except CustomAPIException as e:
            raise e
        except Exception as e:
            raise CustomAPIException('error', str(e))


class MainSettingsSerializer(PositionSettingsSerializer):
    class Meta:
        model = MainSettings
        fields = [
            'take_profit_rate', 'stop_loss_rate', 'trailing_stop_callback_rate',
            'trailing_stop_activation_price_rate', 'short_position_limit',
            'long_position_limit', 'bull_mode', 'bear_mode',
            'signal_source_name', 'amount_usdt', 'coefficient'
        ]

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
            i = Namespace(**data)
            if hasattr(i, 'coefficient'):
                if i.coefficient < 0.001 or i.coefficient > 100:
                    raise CustomAPIException(
                        'coefficient',
                        'Coefficient must be between 0.001 and 100'
                    )
            if i.bull_mode and i.bear_mode:
                raise CustomAPIException(
                    'bull_mode',
                    'Only one mode can be enabled at a time'
                )
            if (
                i.take_profit_rate != 0 and (i.trailing_stop_callback_rate != 0 or
                                             i.trailing_stop_activation_price_rate != 0)
            ):
                raise CustomAPIException(
                    'take_profit_rate',
                    'Take profit rate cannot be set with trailing stop'
                )
            if i.trailing_stop_callback_rate > 0 and i.trailing_stop_activation_price_rate == 0:
                raise CustomAPIException(
                    'trailing_stop_activation_price_rate',
                    'Trailing stop activation price rate is required'
                )
            if i.trailing_stop_callback_rate == 0 and i.trailing_stop_activation_price_rate > 0:
                raise CustomAPIException(
                    'trailing_stop_callback_rate',
                    'Trailing stop price rate is required'
                )
            if i.trailing_stop_callback_rate > 0:
                if i.trailing_stop_callback_rate < 0.1 or i.trailing_stop_callback_rate > 10:
                    raise CustomAPIException(
                        'trailing_stop_callback_rate',
                        'Trailing stop price rate must be between 0.1 and 10'
                    )
            return data
        except CustomAPIException as e:
            raise e
        except Exception as e:
            raise CustomAPIException('error', str(e))


class SymbolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Symbol
        fields = ['symbol', 'is_active', 'data', 'leverage']
        read_only_fields = ['symbol', 'data', 'leverage']


class PositionSerializer(serializers.ModelSerializer):
    leverage = serializers.SlugRelatedField(
        slug_field='leverage', read_only=True, source='symbol'
    )
    settings = PositionSettingsSerializer()

    class Meta:
        model = Position
        fields = [
            'id', 'symbol', 'position_side', 'position_amt', 'entry_price',
            'break_even_price', 'unrealized_profit', 'liquidation_price',
            'notional', 'leverage', 'mark_price', 'update_time', 'is_open',
            'side', 'settings'
        ]


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = [
            'order_id', 'client_order_id', 'position', 'symbol', 'status', 'side',
            'order_type', 'position_side', 'orig_qty', 'stop_price', 'avg_price',
            'activation_price', 'price_rate', 'time'
        ]


class ClosePositionPartialSerializer(serializers.Serializer):
    order_type = serializers.ChoiceField(choices=['MARKET', 'LIMIT'], required=True)
    price_rate = serializers.FloatField(
        min_value=0, max_value=100, default=0, required=False
    )
    quantity_rate = serializers.FloatField(
        min_value=0, max_value=100, required=True
    )

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
            i = Namespace(**data)
            if i.order_type == 'LIMIT':
                if i.price_rate == 0:
                    raise CustomAPIException(
                        'price_rate',
                        'Price rate is required for limit order'
                    )
            elif i.order_type == 'MARKET':
                if i.price_rate > 0:
                    raise CustomAPIException(
                        'price_rate',
                        'Price rate is not allowed for market order. Set to 0'
                    )
            if i.quantity_rate == 0:
                raise CustomAPIException('quantity_rate', 'Quantity rate is required')
            return data
        except CustomAPIException as e:
            raise e
        except Exception as e:
            logger.exception(e)
            raise CustomAPIException('error', str(e))


class IncreasePositionSerializer(serializers.Serializer):
    multiplier = serializers.IntegerField(min_value=2, max_value=10, required=True)


class OpenPositionSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=20, required=True)
    order_type = serializers.ChoiceField(choices=['MARKET', 'LIMIT'], required=True)
    side = serializers.ChoiceField(choices=['BUY', 'SELL'], required=True)
    amount_usdt = serializers.FloatField(required=True)
    leverage = serializers.IntegerField(min_value=1, max_value=20, required=True)
    price = serializers.FloatField(min_value=0, required=True)
    take_profit_rate = serializers.FloatField(min_value=0, max_value=10000, required=True)
    stop_loss_rate = serializers.FloatField(min_value=0, max_value=10000, required=True)
    trailing_stop_callback_rate = serializers.FloatField(min_value=0, max_value=100, required=True)
    trailing_stop_activation_price_rate = serializers.FloatField(min_value=0, max_value=10000, required=True)

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
            i = Namespace(**data)
            try:
                available_positions_count(i.side)
                symbol = Symbol.objects.get(symbol=i.symbol)
                if not symbol.is_active:
                    raise CustomAPIException('symbol', 'Symbol is not active')
                if symbol.get_last_open_position():
                    raise CustomAPIException('symbol', 'Position already open')
            except Symbol.DoesNotExist:
                raise CustomAPIException('symbol', 'Symbol not found')
            if i.amount_usdt <= 0:
                raise CustomAPIException(
                    'amount_usdt', 'Amount in USDT must be greater than zero'
                )
            if i.order_type == 'LIMIT' and i.price <= 0:
                raise CustomAPIException('price', 'Price is required for limit order')
            if i.take_profit_rate != 0 and (i.trailing_stop_callback_rate != 0 or
                                            i.trailing_stop_activation_price_rate != 0):
                raise CustomAPIException(
                    'take_profit_rate',
                    'Take profit rate cannot be set with trailing stop'
                )
            if i.trailing_stop_callback_rate > 0 and i.trailing_stop_activation_price_rate == 0:
                raise CustomAPIException(
                    'trailing_stop_activation_price_rate',
                    'Trailing stop activation price rate is required'
                )
            if i.trailing_stop_callback_rate == 0 and i.trailing_stop_activation_price_rate > 0:
                raise CustomAPIException(
                    'trailing_stop_callback_rate',
                    'Trailing stop price rate is required'
                )
            if i.trailing_stop_callback_rate > 0:
                if i.trailing_stop_callback_rate < 0.1 or i.trailing_stop_callback_rate > 10:
                    raise CustomAPIException(
                        'trailing_stop_callback_rate',
                        'Trailing stop price rate must be between 0.1 and 10'
                    )
            symbol = Symbol.objects.get(symbol=i.symbol)
            if symbol.get_last_open_position():
                raise CustomAPIException('symbol', 'Position already open')
            return data
        except CustomAPIException as e:
            raise e
        except Exception as e:
            logger.exception(e)
            raise CustomAPIException('error', str(e))


class SignalSerializer(serializers.Serializer):
    symbol = serializers.CharField(max_length=20, required=True)
    side = serializers.ChoiceField(choices=['LONG', 'SHORT'], required=True)
    signal_name = serializers.ChoiceField(
        choices=MainSettings.SignalSource.values, required=True
    )

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
            i = Namespace(**data)
            available_positions_count(i.side)
            try:
                symbol = Symbol.objects.get(symbol=i.symbol)
                if not symbol.is_active:
                    raise CustomAPIException('symbol', 'Symbol is not active')
                if symbol.get_last_open_position():
                    raise CustomAPIException('symbol', 'Position already open')
            except Symbol.DoesNotExist:
                raise CustomAPIException('symbol', 'Symbol not found')
            main_settings = MainSettings.objects.first()
            if i.signal_name != main_settings.signal_source_name:
                raise CustomAPIException(
                    'signal_name',
                    f'Signal source name: {i.signal_name} is disabled in settings. '
                    f'Allowed source name: {main_settings.signal_source_name}'
                )
            return data
        except CustomAPIException as e:
            raise e
        except Exception as e:
            logger.exception(e)
            raise CustomAPIException('error', str(e))


def available_positions_count(side: str, amount: int = 1) -> int:
    extra = {'side': side}
    main_settings = MainSettings.objects.first()
    if side in ['LONG', 'BUY']:
        side = 'LONG'
        limit = main_settings.long_position_limit
    elif side in ['SHORT', 'SELL']:
        side = 'SHORT'
        limit = main_settings.short_position_limit
    logger.debug(f'Position limit: {limit}', extra=extra)
    if not limit:
        return amount
    open_positions_count = (
        Position.objects.filter(is_open=True, position_side=side).count()
    )
    logger.debug(f'Open positions count: {open_positions_count}', extra=extra)
    can_open_positions_count = limit - open_positions_count
    logger.debug(f'Can open positions count: {can_open_positions_count}', extra=extra)
    if can_open_positions_count <= 0:
        raise CustomAPIException(
            'side', f'Position limit reached for {side}. Limit: {limit}'
        )
    if amount == 1:
        return 1
    if amount > 1:
        if amount > can_open_positions_count:
            return can_open_positions_count
        return amount


class PriceChangePercentStrategySerializer(serializers.Serializer):
    side = serializers.ChoiceField(choices=['LONG', 'SHORT'], required=True)
    amount = serializers.IntegerField(min_value=1, required=True)

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
            available_count = available_positions_count(data['side'], data['amount'])
            data['amount'] = available_count
            data['side'] = 'BUY' if data['side'] == 'LONG' else 'SELL'
            return data
        except CustomAPIException as e:
            raise e
        except Exception as e:
            logger.exception(e)
            raise CustomAPIException('error', str(e))
