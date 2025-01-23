import logging
import json


logger = logging.getLogger(__name__)


def get_client_ip(request) -> str:
    x_forwarded_for = request.headers.get('x-forwarded-for')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


class ResponseLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            ip = get_client_ip(request)
            if (
                request.content_type == 'application/json' or
                request.method in ['POST', 'PUT', 'PATCH']
            ):
                body = request.body.decode('utf-8')
                request._body = body.encode('utf-8')
                body_json = json.loads(body)
                logger.debug(
                    f'Request from {ip}: {request.method}, {request.path}, {body_json}'
                )
            else:
                logger.debug(
                    f'Request from {ip}: {request.method}, {request.path}'
                )
        except Exception as e:
            logger.exception(e)
        response = self.get_response(request)
        # try:
        #     if hasattr(response, 'data'):
        #         logger.debug(
        #             f'Response: {request.method}, {response.status_code}, '
        #             f'{request.path}, {response.data}'
        #         )
        # except Exception as e:
        #     logger.exception(e)
        return response
