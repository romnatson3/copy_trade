from django.core.management.base import BaseCommand, CommandError
from exchange_binance.tasks import update_symbols


class Command(BaseCommand):
    help = 'Create or update info about all symbols for all exchanges'

    def handle(self, *args, **options):
        try:
            update_symbols()
            self.stdout.write(self.style.SUCCESS('Successfully created or updated symbols for futures'))
        except Exception as e:
            raise CommandError(f'Failed to create or update symbols. Reason: {e}')
