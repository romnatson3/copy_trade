from django.contrib.admin import SimpleListFilter
from exchange_binance.models import Position, Order


class SymbolFilter(SimpleListFilter):
    title = 'Symbol'
    parameter_name = 'symbol'

    def lookups(self, request, model_admin):
        symbols = Position.objects.values_list('symbol', flat=True).distinct()
        return [(symbol, symbol) for symbol in symbols]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(symbol=self.value())
        return queryset


class OrderSymbolFilter(SimpleListFilter):
    title = 'Symbol'
    parameter_name = 'symbol'

    def lookups(self, request, model_admin):
        symbols = Order.objects.values_list('symbol', flat=True).distinct()
        return [(symbol, symbol) for symbol in symbols]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(symbol=self.value())
        return queryset
