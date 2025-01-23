import logging
from django.conf import settings


class CustomFormatter(logging.Formatter):
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
        formatter = logging.Formatter(self._fmt)
        record.__dict__.setdefault('account', '---')
        record.__dict__.setdefault('symbol', '---------------')
        record.__dict__.setdefault('side', '----')
        record.__dict__.setdefault('id', '-----------')
        record.symbol = f'{str(record.symbol):<15.15}'
        if record.levelno == settings.TRACE_LEVEL_NUM:
            record.levelname = 'TRACE'
            formatter = logging.Formatter(self.trace_fmt)
        if record.levelno == logging.DEBUG:
            formatter = logging.Formatter(self.debug_fmt)
        if record.levelno == logging.INFO:
            formatter = logging.Formatter(self.info_fmt)
        if record.levelno == logging.WARNING:
            formatter = logging.Formatter(self.warning_fmt)
        if record.levelno == logging.CRITICAL:
            formatter = logging.Formatter(self.critical_fmt)
        if record.levelno == logging.ERROR:
            formatter = logging.Formatter(self.error_fmt)
        formatter.datefmt = '%d-%m-%Y %H:%M:%S'
        return formatter.format(record)
