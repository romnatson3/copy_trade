import logging
from exchange_binance.models import (
    Symbol, Position, Order, MainSettings, MasterAccount, CopyTradeAccount, PositionSettings
)
from exchange_binance.serializers import (
    SymbolSerializer, PositionSerializer, OrderSerializer,
    MainSettingsSerializer, MasterAccountBalanceSerializer, CopyTradeAccountSerializer,
    CustomTokenObtainPairSerializer, PositionSettingsSerializer,
    ClosePositionPartialSerializer, IncreasePositionSerializer,
    OpenPositionSerializer, DummyClosePositionsSerializer,
    MasterAccountCredentialsSerializer, PriceChangePercentStrategySerializer
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiExample
from celery.exceptions import TimeLimitExceeded
from exchange_binance import tasks


logger = logging.getLogger(__name__)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


example_delete_400 = OpenApiExample(
    name='',
    description='',
    value={
        'detail': [
            {
                'position_id': 1,
                'status': 'failed',
                'detail': 'Error message'
            }
        ]
    },
    status_codes=['400'],
)


@extend_schema(tags=['master account credentials'])
@extend_schema_view(
    get=extend_schema(
        summary='Get master account credentials',
    ),
    put=extend_schema(
        summary='Update master account credentials',
        request=MasterAccountCredentialsSerializer,
    )
)
class MasterAccountCredentialsViewAPIView(APIView):
    def get(self, request):
        master_account = MasterAccount.objects.first()
        serializer = MasterAccountCredentialsSerializer(master_account)
        return Response(serializer.data)

    def put(self, request):
        master_account = MasterAccount.objects.first()
        serializer = MasterAccountCredentialsSerializer(
            master_account, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['master account balances'])
@extend_schema_view(
    get=extend_schema(
        summary='Get master account balances',
    )
)
class MasterAccountBalanceViewAPIView(APIView):
    def get(self, request):
        serializer = MasterAccountBalanceSerializer(MasterAccount.objects.first())
        return Response(serializer.data)


@extend_schema(tags=['copy trade accounts'])
@extend_schema_view(
    list=extend_schema(
        summary='Get all copy trade accounts',
    ),
    retrieve=extend_schema(
        summary='Get copy trade account by id',
    ),
    create=extend_schema(
        summary='Create a new copy trade account',
        request=CopyTradeAccountSerializer,
    ),
    update=extend_schema(
        summary='Update copy trade account by id',
        request=CopyTradeAccountSerializer,
    ),
    destroy=extend_schema(
        summary='Delete copy trade account by id',
    )
)
class CopyTradeAccountViewSet(viewsets.ViewSet):
    def list(self, request):
        queryset = CopyTradeAccount.objects.all()
        serializer = CopyTradeAccountSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = CopyTradeAccount.objects.all()
        account = get_object_or_404(queryset, id=pk)
        serializer = CopyTradeAccountSerializer(account)
        return Response(serializer.data)

    def create(self, request):
        serializer = CopyTradeAccountSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        queryset = CopyTradeAccount.objects.all()
        account = get_object_or_404(queryset, id=pk)
        serializer = CopyTradeAccountSerializer(account, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        queryset = CopyTradeAccount.objects.all()
        account = get_object_or_404(queryset, id=pk)
        logger.warning(
            'Deleted copy trade account', extra={'account': account.name}
        )
        account.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(
    list=extend_schema(
        summary='Get all symbols and their data',
    ),
    retrieve=extend_schema(
        summary='Get symbol by symbol name',
    ),
    update=extend_schema(
        summary='Update symbol active status by symbol name',
        request=SymbolSerializer,
    )
)
class SymbolViewSet(viewsets.ViewSet):
    lookup_field = 'name'

    def list(self, request):
        queryset = Symbol.objects.all()
        serializer = SymbolSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, name=None):
        queryset = Symbol.objects.all()
        symbol = get_object_or_404(queryset, symbol=name)
        serializer = SymbolSerializer(symbol)
        return Response(serializer.data)

    def update(self, request, name=None):
        queryset = Symbol.objects.all()
        symbol = get_object_or_404(queryset, symbol=name)
        serializer = SymbolSerializer(symbol, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['main settings'])
@extend_schema_view(
    get=extend_schema(
        summary='Get main settings',
    ),
    put=extend_schema(
        summary='Update main settings',
        request=MainSettingsSerializer,
    )
)
class MainSettingsAPIView(APIView):
    def get(self, request):
        main_settings = MainSettings.objects.first()
        serializer = MainSettingsSerializer(main_settings)
        return Response(serializer.data)

    def put(self, request):
        main_settings = MainSettings.objects.first()
        serializer = MainSettingsSerializer(main_settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['positions'])
@extend_schema_view(
    put=extend_schema(
        summary='Update position sl, tp, ts settings by position id',
        request=PositionSettingsSerializer,
    )
)
class PositionSettingsAPIView(APIView):
    queryset = PositionSettings.objects.filter(position__is_open=True)

    def put(self, request, id=None):
        settings = get_object_or_404(self.queryset.all(), position_id=id)
        serializer = PositionSettingsSerializer(settings, data=request.data)
        if serializer.is_valid():
            changed_fields = []
            for field, value in serializer.validated_data.items():
                if getattr(settings, field) != value:
                    changed_fields.append(field)
            if changed_fields:
                result: dict = tasks.replacing_orders.delay(
                    settings.position.id, changed_fields, serializer.validated_data
                ).get()
                if result.get('error'):
                    return Response(
                        {'detail': result['detail']},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'detail': 'No changes detected.'},
                    status=status.HTTP_200_OK
                )
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['orders'])
@extend_schema_view(
    get=extend_schema(
        summary='Get all new orders',
    )
)
class OrderListAPIView(APIView):
    def get(self, request):
        queryset = Order.objects.filter(status__in=['NEW', 'PARTIALLY_FILLED'])
        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data)


@extend_schema(tags=['orders'])
@extend_schema_view(
    get=extend_schema(
        summary='Get order by order id',
    ),
    delete=extend_schema(
        summary='Cancel order by order id',
    )
)
class OrderAPIView(APIView):
    def get(self, request, order_id=None):
        order = get_object_or_404(Order, order_id=order_id)
        serializer = OrderSerializer(order)
        return Response(serializer.data)

    def delete(self, request, order_id=None):
        order = get_object_or_404(Order, order_id=order_id)
        extra = {'symbol': order.symbol, 'side': order.side, 'id': order.order_id}
        try:
            order.cancel()
            msg = 'Canceled order successfully'
        except Exception as e:
            logger.exception(e, extra=extra)
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        logger.warning(msg, extra=extra)
        return Response({'detail': msg}, status=status.HTTP_200_OK)


@extend_schema(tags=['positions'])
@extend_schema_view(
    get=extend_schema(
        summary='Get position data by position id',
    ),
    put=extend_schema(
        summary='Close position partially by position id. Use MARKET or LIMIT order type.',
        request=ClosePositionPartialSerializer,
    ),
    delete=extend_schema(
        summary='Close all positions',
        responses={
            200: DummyClosePositionsSerializer,
            400: DummyClosePositionsSerializer
        },
        examples=[example_delete_400]
    )
)
class PositionAPIView(APIView):
    queryset = Position.objects.filter(is_open=True)

    def get(self, request, id=None):
        position = get_object_or_404(self.queryset.all(), pk=id)
        serializer = PositionSerializer(position)
        return Response(serializer.data)

    def put(self, request, id=None):
        position = get_object_or_404(self.queryset.all(), pk=id)
        serializer = ClosePositionPartialSerializer(data=request.data)
        if serializer.is_valid():
            result: dict = tasks.place_market_or_limit_order.delay(
                position.id, serializer.validated_data
            ).get()
            if result.get('error'):
                return Response({'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'detail': result['detail']}, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id=None):
        position = get_object_or_404(self.queryset.all(), pk=id)
        result: dict = tasks.close_positions.delay(position_id=position.id).get()
        if result.get('error'):
            return Response({'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': result['detail']}, status=status.HTTP_200_OK)


@extend_schema(tags=['positions'])
@extend_schema_view(
    put=extend_schema(
        summary='Increase position by position id',
        request=IncreasePositionSerializer,
    )
)
class IncreasePositionAPIView(APIView):
    queryset = Position.objects.filter(is_open=True)

    def put(self, request, id=None):
        position = get_object_or_404(self.queryset.all(), pk=id)
        serializer = IncreasePositionSerializer(data=request.data)
        if serializer.is_valid():
            result: dict = tasks.increase_position.delay(
                position.id, serializer.validated_data
            ).get()
            if result.get('error'):
                return Response({'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'detail': result['detail']}, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['positions'])
@extend_schema_view(
    delete=extend_schema(
        summary='Close all positions',
        responses={
            200: DummyClosePositionsSerializer,
            400: DummyClosePositionsSerializer
        },
        examples=[example_delete_400]
    )
)
class CloseAllPositionsAPIView(APIView):
    def delete(self, request):
        result: dict = tasks.close_positions.delay().get()
        if result.get('error'):
            return Response({'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': result['detail']}, status=status.HTTP_200_OK)


@extend_schema(tags=['positions'])
@extend_schema_view(
    delete=extend_schema(
        summary='Close all profitable positions',
        responses={
            200: DummyClosePositionsSerializer,
            400: DummyClosePositionsSerializer
        },
        examples=[example_delete_400]
    )
)
class CloseAllProfitablePositionsAPIView(APIView):
    def delete(self, request):
        result: dict = tasks.close_positions.delay(unrealized_profit=True).get()
        if result.get('error'):
            return Response({'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': result['detail']}, status=status.HTTP_200_OK)


@extend_schema(tags=['positions'])
@extend_schema_view(
    get=extend_schema(
        summary='Get all open positions',
    ),
    post=extend_schema(
        summary='Open new position',
        request=OpenPositionSerializer,
        responses={
            200: OpenPositionSerializer,
            400: OpenPositionSerializer
        },
        examples=[
            OpenApiExample(
                name='',
                description='',
                value={
                    'detail': 'Message'
                },
                status_codes=['200', '400']
            )
        ]
    ),
)
class PositionListAPIView(APIView):
    queryset = Position.objects.filter(is_open=True)

    def get(self, request):
        serializer = PositionSerializer(self.queryset.all(), many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = OpenPositionSerializer(data=request.data)
        if serializer.is_valid():
            try:
                result: dict = tasks.open_position_manually.delay(serializer.validated_data).get()
            except TimeLimitExceeded:
                return Response(
                    {'detail': 'Timeout error'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if result.get('error'):
                return Response({'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'detail': result['detail']}, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['price change percent strategy'])
@extend_schema_view(
    post=extend_schema(
        summary='Price change percent strategy',
        request=PriceChangePercentStrategySerializer,
        responses={
            200: PriceChangePercentStrategySerializer,
            400: PriceChangePercentStrategySerializer
        },
        examples=[
            OpenApiExample(
                name='',
                description='',
                value={
                    'detail': 'Message'
                },
                status_codes=['200', '400']
            )
        ]
    ),
)
class PriceChangePercentStrategyAPIView(APIView):
    def post(self, request):
        serializer = PriceChangePercentStrategySerializer(data=request.data)
        if serializer.is_valid():
            result: dict = (
                tasks.price_change_percent_strategy
                .delay(serializer.validated_data).get()
            )
            if result.get('error'):
                return Response(
                    {'detail': result['detail']}, status=status.HTTP_400_BAD_REQUEST
                )
            return Response({'detail': result['detail']}, status=status.HTTP_200_OK)
        logger.warning(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
