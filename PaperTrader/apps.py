from django.apps import AppConfig


class PapertraderConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'PaperTrader'

    def ready(self):
        from . import scheduler
        scheduler.start()
