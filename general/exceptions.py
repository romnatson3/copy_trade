from rest_framework.exceptions import APIException


class CustomAPIException(APIException):
    status_code = 400

    def __init__(self, field, detail):
        self.detail = {
            field: [detail]
        }


class AcquireLockException(Exception):
    pass


class LimitUsageException(Exception):
    pass


class PlaceOrderException(Exception):
    pass


class CancelOrderException(Exception):
    pass
