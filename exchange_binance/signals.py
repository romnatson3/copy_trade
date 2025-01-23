import logging
import os
from django.core.cache import cache
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver
from exchange_binance.models import (
    MainSettings, Position, PositionSettings, MasterAccount
)
from exchange_binance import tasks


logger = logging.getLogger(__name__)


@receiver(post_migrate)
def create_main_settings(sender, **kwargs):
    if not MainSettings.objects.exists():
        MainSettings.objects.create()


@receiver(post_migrate)
def create_master_account(sender, **kwargs):
    if not MasterAccount.objects.exists():
        MasterAccount.objects.create(name='Binance Master Account')


@receiver(post_save, sender=Position)
def create_position(sender, instance, created, **kwargs):
    extra = {'symbol': instance.symbol, 'side': instance.side, 'id': instance.id}
    if created:
        main_settings = MainSettings.objects.first()
        settings = dict(
            take_profit_rate=main_settings.take_profit_rate,
            stop_loss_rate=main_settings.stop_loss_rate,
            trailing_stop_callback_rate=main_settings.trailing_stop_callback_rate,
            trailing_stop_activation_price_rate=main_settings.trailing_stop_activation_price_rate
        )
        manually_settings = cache.get(f'open_position_manually_{instance.symbol}')
        if manually_settings:
            logger.trace('Found manually settings in cahce', extra=extra)
            settings.update(manually_settings)
            cache.delete(f'open_position_manually_{instance.symbol}')
            logger.trace('Deleted manually settings from cache', extra=extra)
        PositionSettings.objects.create(position=instance, **settings)
        logger.info(f'Created position settings: {settings}', extra=extra)
        tasks.placing_orders_after_opening_position.delay(instance.id)
    else:
        if not instance.is_open:
            tasks.cancel_all_open_orders.delay(instance.symbol.symbol)
