from django.urls import path
from rest_framework.routers import DefaultRouter
from exchange_binance.views.api import (
    SymbolViewSet, PositionAPIView, PositionSettingsAPIView, PositionListAPIView,
    OrderAPIView, OrderListAPIView, MainSettingsAPIView, CopyTradeAccountViewSet,
    IncreasePositionAPIView, CloseAllPositionsAPIView,
    CloseAllProfitablePositionsAPIView, MasterAccountBalanceViewAPIView,
    MasterAccountCredentialsViewAPIView, PriceChangePercentStrategyAPIView
)


urlpatterns = [
    path('main_settings', MainSettingsAPIView.as_view(), name='main_settings'),
    path('positions/close_all', CloseAllPositionsAPIView.as_view(), name='positions_close_all'),
    path('positions/close_all_profitable', CloseAllProfitablePositionsAPIView.as_view(), name='positions_close_all_profitable'),
    path('positions', PositionListAPIView.as_view(), name='positions_list'),
    path('positions/<int:id>', PositionAPIView.as_view(), name='positions_detail'),
    path('positions/<int:id>/settings', PositionSettingsAPIView.as_view(), name='positions_settings'),
    path('positions/<int:id>/increase', IncreasePositionAPIView.as_view(), name='positions_increase'),
    path('orders', OrderListAPIView.as_view(), name='orders'),
    path('orders/<int:order_id>', OrderAPIView.as_view(), name='orders_detail'),
    path('master_account_balances', MasterAccountBalanceViewAPIView.as_view(), name='master_account_balances'),
    path('master_account_credentials', MasterAccountCredentialsViewAPIView.as_view(), name='master_account_credentials'),
    path('price_change_percent_strategy', PriceChangePercentStrategyAPIView.as_view(), name='price_change_percent_strategy'),
]

router = DefaultRouter(trailing_slash=False)
router.register(r'symbols', SymbolViewSet, basename='symbols')
router.register(r'copy_trade_account', CopyTradeAccountViewSet, basename='copy_trade_account')

urlpatterns += router.urls
