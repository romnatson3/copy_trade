from django.apps import AppConfig


class ExchangeBinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'exchange_binance'

    def ready(self):
        import exchange_binance.signals
