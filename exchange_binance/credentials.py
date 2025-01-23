from exchange_binance.models import MasterAccount


class Binance():
    def _get_api_key(self):
        key = MasterAccount.objects.values_list('api_key', flat=True).first()
        if not key:
            raise ValueError('API Key is not set in Master Account')
        return key

    def _get_api_secret(self):
        secret = MasterAccount.objects.values_list('api_secret', flat=True).first()
        if not secret:
            raise ValueError('API Secret is not set in Master Account')
        return secret

    def _get_testnet(self):
        testnet = MasterAccount.objects.values_list('testnet', flat=True).first()
        if testnet is None:
            return False
        return testnet

    @property
    def api_key(self):
        return self._get_api_key()

    @property
    def api_secret(self):
        return self._get_api_secret()

    @property
    def testnet(self):
        return self._get_testnet()


binance = Binance()
