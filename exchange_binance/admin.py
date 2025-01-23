import logging
from datetime import datetime
from django.contrib import admin
from exchange_binance.models import (
    Symbol, Position, Order, MainSettings, CopyTradeAccount, PositionSettings,
    MasterAccount, CopyTradeOrder
)
from general.utils import get_pretty_dict
from exchange_binance.filters import SymbolFilter, OrderSymbolFilter


logger = logging.getLogger(__name__)


admin.site.site_header = 'Copy Trade'
admin.site.site_title = 'Copy Trade'
admin.site.index_title = 'Copy Trade'


@admin.register(MasterAccount)
class MasterAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'testnet', 'api_key', 'api_secret', 'wallet_balance',
        'available_balance', 'margin_balance', 'cross_unrealized_pnl',
        'unrealized_profit', 'updated_at'
    )
    list_display_links = ('id', 'name')


@admin.register(CopyTradeAccount)
class CopyTradeAccountAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'use_proxy', 'api_key', 'api_secret', 'proxy', 'wallet_balance',
        'available_balance', 'margin_balance', 'cross_unrealized_pnl',
        'unrealized_profit', 'updated_at'
    )
    ordering = ('-id',)
    readonly_fields = ('updated_at', 'created_at')
    list_display_links = ('id', 'name')


@admin.register(Symbol)
class SymbolAdmin(admin.ModelAdmin):
    list_display = ('is_active', 'symbol', 'leverage', 'market_price', 'updated_at')
    search_fields = ('symbol',)
    fields = ('symbol', 'is_active', 'pretty_data', 'leverage', 'updated_at', 'created_at')
    ordering = ('symbol',)
    readonly_fields = ('symbol', 'pretty_data', 'updated_at', 'created_at')
    list_display_links = ('symbol',)
    list_filter = ('is_active',)

    @admin.display(description='Data')
    def pretty_data(self, obj) -> str:
        return get_pretty_dict(obj.data)

    @admin.display(description='Market Price', ordering='market_price')
    def market_price(self, obj) -> str:
        return obj.market_price


@admin.register(MainSettings)
class MainSettingsAdmin(admin.ModelAdmin):
    list_display = [i.name for i in MainSettings._meta.fields]
    fields = [i.name for i in MainSettings._meta.fields]
    ordering = ('-id',)
    readonly_fields = (
        'updated_at', 'created_at', 'id'
    )
    list_display_links = ('id',)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(PositionSettings)
class PositionSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'position', 'take_profit_rate', 'stop_loss_rate',
        'trailing_stop_callback_rate', 'trailing_stop_activation_price_rate',
        'updated_at'
    )
    fields = (
        'id', 'position', 'take_profit_rate', 'stop_loss_rate', 'trailing_stop_callback_rate',
        'trailing_stop_activation_price', 'updated_at', 'created_at'
    )
    ordering = ('-id',)
    readonly_fields = ('position', 'updated_at', 'created_at')
    list_display_links = ('position',)

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False


class PositionSettingsInline(admin.TabularInline):
    model = PositionSettings
    fields = (
        'take_profit_rate', 'stop_loss_rate', 'trailing_stop_callback_rate',
        'trailing_stop_activation_price_rate', 'updated_at'
    )
    ordering = ('-id',)
    readonly_fields = ('updated_at',)
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_id', 'client_order_id', 'symbol', 'position', 'status', 'side',
        'order_type', 'orig_type', 'price', 'avg_price', 'position_side',
        'orig_qty', 'stop_price', 'activation_price', 'price_rate', '_time'
    )
    search_fields = ('symbol__symbol', 'client_order_id', 'order_id')
    ordering = ('-time',)
    list_display_links = ('order_id',)
    list_filter = (
        'status', 'side', 'order_type', 'position_side', OrderSymbolFilter
    )
    list_per_page = 500

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    @admin.display(description='Time')
    def _time(self, obj) -> str:
        date_time = (
            datetime.fromtimestamp(obj.time / 1000)
            .strftime('%d-%m-%Y %H:%M:%S.%f')[:-3]
        )
        return date_time


class OrderInline(admin.TabularInline):
    model = Order
    fields = (
        'order_id', 'status', 'side', 'order_type', 'orig_type', 'price', 'avg_price',
        'position_side', 'orig_qty', 'stop_price', 'activation_price',
        'price_rate', '_time'
    )
    ordering = ('-time',)
    readonly_fields = ('_time',)
    extra = 0

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description='Time')
    def _time(self, obj) -> str:
        date_time = (
            datetime.fromtimestamp(obj.time / 1000)
            .strftime('%d-%m-%Y %H:%M:%S.%f')[:-3]
        )
        return date_time


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'is_open', 'symbol', 'position_side', 'notional', 'position_amt',
        'entry_price', 'mark_price', 'unrealized_profit', '_update_time'
    )
    search_fields = ('symbol__symbol',)
    fields = (
        'id', 'is_open', 'symbol', 'position_side', 'side', 'notional',
        'position_amt', 'entry_price', 'mark_price', 'unrealized_profit',
        'updated_at', 'created_at'
    )
    ordering = ('-id',)
    readonly_fields = (
        'id', 'symbol', 'position_side', 'side', 'notional', 'position_amt',
        'entry_price', 'mark_price', 'unrealized_profit',
        'updated_at', 'created_at'
    )
    list_display_links = ('symbol',)
    list_filter = ('is_open', SymbolFilter)
    inlines = [PositionSettingsInline, OrderInline]
    list_per_page = 500

    @admin.display(description='Update Time')
    def _update_time(self, obj) -> str:
        if not obj.update_time:
            return ''
        date_time = (
            datetime.fromtimestamp(obj.update_time / 1000)
            .strftime('%d-%m-%Y %H:%M:%S.%f')[:-3]
        )
        return date_time

    class Media:
        css = {
            'all': ('exchange_binance/css/inline.css',)
        }


@admin.register(CopyTradeOrder)
class CopyTradeOrderAdmin(OrderAdmin):
    list_display = (
        'copy_trade_account', 'symbol', 'order_id', 'master_order',
        'status', 'side', 'order_type', 'orig_type', 'avg_price', 'position_side',
        'orig_qty', 'stop_price', 'activation_price', 'price_rate', '_time'
    )
    list_filter = ('order_type', 'copy_trade_account', 'orig_type')
    search_fields = ('symbol__symbol', 'copy_trade_account__name', 'order_id')
