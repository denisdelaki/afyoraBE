from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        self._patch_django_template_context_copy()

    @staticmethod
    def _patch_django_template_context_copy():
        """Patch Django 4.2 context copying for Python 3.14."""
        import sys
        from django import VERSION as DJANGO_VERSION
        from django.template.context import BaseContext

        if sys.version_info < (3, 14) or DJANGO_VERSION >= (5, 0):
            return

        if getattr(BaseContext, '_afyora_py314_copy_patch', False):
            return

        def _base_context_copy(self):
            duplicate = self.__class__.__new__(self.__class__)
            duplicate.__dict__ = self.__dict__.copy()
            duplicate.dicts = self.dicts[:]
            return duplicate

        BaseContext.__copy__ = _base_context_copy
        BaseContext._afyora_py314_copy_patch = True
