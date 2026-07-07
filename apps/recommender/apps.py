from django.apps import AppConfig

class RecommenderConfig(AppConfig):
    name = "apps.recommender"

    def ready(self):
        from . import signals