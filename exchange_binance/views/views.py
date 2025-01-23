import logging
import json
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound
from django.views.generic import View
from django.utils.decorators import method_decorator
from django.conf import settings
from general.utils import get_client_ip
from exchange_binance import tasks
from exchange_binance.serializers import SignalSerializer
from general.exceptions import CustomAPIException


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class BinanceWebhookView(View):
    authentication_classes = []
    permission_classes = []

    def dispatch(self, request, *args, **kwargs):
        client_ip = get_client_ip(request)
        if client_ip not in settings.SIGNAL_SOURCE_IPS:
            logger.info(f'Request from unknown IP: {client_ip}')
            # return HttpResponseNotFound('IP not in list.')
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs) -> HttpResponse:
        try:
            data = json.loads(request.body)
            logger.info(f'Received signal: {data}')
            serializer = SignalSerializer(data=data)
            if serializer.is_valid():
                symbol = serializer.validated_data['symbol']
                side = serializer.validated_data['side']
                side = 'BUY' if side == 'LONG' else 'SELL'
                tasks.open_position_signal.delay(symbol, side)
                return JsonResponse(serializer.data, status=200)
            logger.warning(f'{serializer.errors}')
            return JsonResponse(serializer.errors, status=400)
        except CustomAPIException as e:
            logger.warning(f'{e.detail}')
            return JsonResponse(e.detail, status=400)
        except Exception as e:
            logger.exception(e)
            return JsonResponse({'detail': 'Unknown error'}, status=500)
