import logging
import json
import re
import time
from typing import Optional
from datetime import datetime
from django.utils.safestring import mark_safe
from django.core.cache import cache
from django_redis import get_redis_connection
from general.exceptions import AcquireLockException, LimitUsageException


logger = logging.getLogger(__name__)
connection = get_redis_connection('default')


class TaskLock():
    def __init__(
        self,
        key: str,
        use_limit_usage: bool = False,
        timeout: Optional[int] = 10,
        blocking: bool = False,
        blocking_timeout: Optional[int] = 1
    ) -> None:
        self.key = key
        self.timeout = timeout
        self.blocking = blocking
        self.blocking_timeout = blocking_timeout
        self.sleep = 0.001,
        self.use_limit_usage = use_limit_usage

    def limit_usage(self) -> bool:
        if self.use_limit_usage:
            return cache.get('limit_usage_too_high')
        return False

    def acquire(self) -> bool:
        if not self.blocking:
            return self.do_acquire()
        stop_trying_at = None
        if self.blocking_timeout:
            stop_trying_at = time.monotonic() + self.blocking_timeout
        while True:
            if self.do_acquire():
                return True
            if not self.blocking:
                return False
            if stop_trying_at and time.monotonic() > stop_trying_at:
                return False
            time.sleep(self.sleep)

    def do_acquire(self) -> bool:
        if connection.set(self.key, 1, nx=True, ex=self.timeout):
            return True
        return False

    def release(self) -> bool:
        return connection.delete(self.key) == 1

    def locked(self) -> bool:
        return connection.exists(self.key) == 1

    def __enter__(self):
        if self.limit_usage():
            raise LimitUsageException('Limit usage is too high')
        if self.acquire():
            return self
        raise AcquireLockException('Failed to acquire lock')

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()


def get_pretty_dict(data) -> str:
    data = dict(sorted(data.items()))
    data = json.dumps(data, indent=2)
    data = re.sub('"', "'", data)
    return mark_safe(
        f'<pre style="font-size: 1.05em; font-family: monospace;">{data}</pre>'
    )


def get_pretty_text(obj) -> str:
    text = json.dumps(obj, indent=2)
    l = []
    for k, v in obj.items():
        if isinstance(v, float):
            l.append(f'{k}: {v:.5f}')
        elif isinstance(v, list):
            l.append(
                f'{k}: <pre style="font-size: 1.05em; font-family: monospace;">'
                f'{json.dumps(v, indent=2)}</pre>'
            )
        else:
            l.append(f'{k}: {v}')
    text = '<br>'.join(l)
    return mark_safe(
        '<span style="font-size: 1.05em; font-family: monospace;'
        f'white-space: wrap;">{text}</span>'
    )


def sort_data(parameters: dict, template: dict) -> dict:
    sorted_data = {
        i: parameters.get(i)
        for i in template.keys()
    }
    return sorted_data


def convert_dict_values(data: dict) -> dict[str, str | int | float]:
    for k, v in data.items():
        if isinstance(v, str):
            if re.search(r'^(?!.*:)[+-]?\d+\.\d+$', v):
                data[k] = round(float(v), 10)
            elif re.search(r'^[-+]?\d+$', v):
                data[k] = int(v)
            elif re.search(r'\w', v):
                data[k] = v
            elif v == '':
                data[k] = None
            if k in ['uTime', 'cTime', 'pTime', 'fillTime', 'ts']:
                try:
                    data[k] = datetime.fromtimestamp(int(v) / 1000).strftime('%d-%m-%Y %H:%M:%S.%f')
                except ValueError:
                    data[k] = v
    return data


def get_client_ip(request) -> str:
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip
