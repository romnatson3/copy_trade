from __future__ import absolute_import, unicode_literals
import logging
import os
from django.conf import settings
from celery import Celery
from celery.app.log import TaskFormatter as CeleryTaskFormatter
from celery.signals import after_setup_task_logger, after_setup_logger
from celery._state import get_current_task
from celery.schedules import crontab


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'copy_trade.settings')

app = Celery('copy_trade')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


app.conf.update(
    task_default_queue='default',
    task_routes={
        'exchange_binance.tasks.update_symbols': {'queue': 'default'},
        'exchange_binance.tasks.get_limit_usage': {'queue': 'default'},
        'exchange_binance.tasks.update_balances': {'queue': 'default'},
        'exchange_binance.tasks.update_positions': {'queue': 'binance'},
        'exchange_binance.tasks.update_open_orders': {'queue': 'binance'},
        'exchange_binance.tasks.cancel_all_open_orders': {'queue': 'binance'},
        'exchange_binance.tasks.place_market_or_limit_order': {'queue': 'binance'},
        'exchange_binance.tasks.increase_position': {'queue': 'binance'},
        'exchange_binance.tasks.replacing_orders': {'queue': 'binance'},
        'exchange_binance.tasks.close_positions': {'queue': 'binance'},
        'exchange_binance.tasks.open_position_signal': {'queue': 'binance'},
        'exchange_binance.tasks.open_position_manually': {'queue': 'binance'},
        'exchange_binance.tasks.copy_trade_order': {'queue': 'binance'},
        'exchange_binance.tasks.copy_trade_account': {'queue': 'binance'},
        'exchange_binance.tasks.price_change_percent_strategy': {'queue': 'binance'},
        'exchange_binance.tasks.placing_orders_after_opening_position': {'queue': 'binance'},
        'exchange_binance.tasks.run_websocket_binance_market_price': {'queue': 'websocket_binance_market_price'},
        'exchange_binance.tasks.run_websocket_binance_user_data': {'queue': 'websocket_binance_user_data'},
    },
    beat_schedule={
        'update_balances': {
            'task': 'exchange_binance.tasks.update_balances',
            'schedule': 5,
        },
        'get_limit_usage': {
            'task': 'exchange_binance.tasks.get_limit_usage',
            'schedule': 5
        },
        'update_positions': {
            'task': 'exchange_binance.tasks.update_positions',
            'schedule': 5,
        },
        # 'update_open_orders': {
        #     'task': 'exchange_binance.tasks.update_open_orders',
        #     'schedule': 10,
        # },
        'update_symbols': {
            'task': 'exchange_binance.tasks.update_symbols',
            'schedule': crontab(minute=0, hour=0),
        },
        'run_websocket_binance_market_price': {
            'task': 'exchange_binance.tasks.run_websocket_binance_market_price',
            'schedule': crontab(minute='*/1'),
        },
        'run_websocket_binance_user_data': {
            'task': 'exchange_binance.tasks.run_websocket_binance_user_data',
            'schedule': crontab(minute='*/1'),
        },
    }
)


class TaskFormatter(CeleryTaskFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        gray = '\033[90m'
        cyan = '\033[36m'
        green = '\033[32m'
        yellow = '\033[33m'
        purple = '\033[35m'
        red = '\033[31m'
        reset = '\033[0m'
        self.trace_fmt = gray + self._fmt + reset
        # self.info_fmt = cyan + self._fmt + reset
        self.info_fmt = self._fmt
        self.debug_fmt = green + self._fmt + reset
        self.warning_fmt = yellow + self._fmt + reset
        self.critical_fmt = purple + self._fmt + reset
        self.error_fmt = red + self._fmt + reset

    def format(self, record):
        formatter = CeleryTaskFormatter(self._fmt)
        task = get_current_task()
        if task and task.request:
            short_task_id = task.request.id.split('-')[0]
            record.__dict__.update(short_task_id=short_task_id)
        else:
            record.__dict__.setdefault('short_task_id', '--------')
        record.__dict__.setdefault('account', '---')
        record.__dict__.setdefault('symbol', '---------------')
        record.__dict__.setdefault('side', '----')
        record.__dict__.setdefault('id', '-----------')
        record.symbol = f'{str(record.symbol):<15.15}'
        if record.levelno == settings.TRACE_LEVEL_NUM:
            record.levelname = 'TRACE'
            formatter = CeleryTaskFormatter(self.trace_fmt)
        if record.levelno == logging.DEBUG:
            formatter = CeleryTaskFormatter(self.debug_fmt)
        if record.levelno == logging.INFO:
            formatter = CeleryTaskFormatter(self.info_fmt)
        if record.levelno == logging.WARNING:
            formatter = CeleryTaskFormatter(self.warning_fmt)
        if record.levelno == logging.CRITICAL:
            formatter = CeleryTaskFormatter(self.critical_fmt)
        if record.levelno == logging.ERROR:
            formatter = CeleryTaskFormatter(self.error_fmt)
        formatter.datefmt = '%d-%m-%Y %H:%M:%S'
        return formatter.format(record)


@after_setup_logger.connect
@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    for handler in logger.handlers:
        tf = TaskFormatter(
            '[%(asctime)s.%(msecs)03d] %(short_task_id)s %(levelname)-8s '
            '%(account)-3s %(symbol)s %(side)-4s %(id)-11s %(message)s'
        )
        tf.datefmt = '%d-%m-%Y %H:%M:%S'
        handler.setFormatter(tf)
