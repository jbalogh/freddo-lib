import os
import sys
import warnings
from importlib import import_module

from celery.loaders.base import BaseLoader

DEFAULT_CONFIG_MODULE = "celeryconfig"

DEFAULT_SETTINGS = {
    "DEBUG": False,
    "ADMINS": (),
    "DATABASE_ENGINE": "sqlite3",
    "DATABASE_NAME": "celery.sqlite",
    "INSTALLED_APPS": ("celery", ),
    "CELERY_IMPORTS": (),
    "CELERY_TASK_ERROR_WHITELIST": (),
}

DEFAULT_UNCONFIGURED_SETTINGS = {
    "CELERY_RESULT_BACKEND": "amqp",
}


class NotConfigured(UserWarning):
    """Celery has not been configured, as no config module has been found."""


def wanted_module_item(item):
    return not item.startswith("_")


class Settings(dict):

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr_(self, key, value):
        self[key] = value


class Loader(BaseLoader):
    """The default loader.

    See the FAQ for example usage.

    """

    def setup_settings(self, settingsdict):
        settings = Settings(DEFAULT_SETTINGS, **settingsdict)
        installed_apps = set(list(DEFAULT_SETTINGS["INSTALLED_APPS"]) + \
                             list(settings.INSTALLED_APPS))
        settings.INSTALLED_APPS = tuple(installed_apps)
        settings.CELERY_TASK_ERROR_WHITELIST = tuple(
                getattr(import_module(mod), cls)
                    for fqn in settings.CELERY_TASK_ERROR_WHITELIST
                        for mod, cls in (fqn.rsplit('.', 1), ))

        return settings

    def import_from_cwd(self, module, imp=import_module):
        """Import module, but make sure it finds modules
        located in the current directory.

        Modules located in the current directory has
        precedence over modules located in ``sys.path``.
        """
        cwd = os.getcwd()
        if cwd in sys.path:
            return imp(module)
        sys.path.insert(0, cwd)
        try:
            return imp(module)
        finally:
            try:
                sys.path.remove(cwd)
            except ValueError:
                pass

    def read_configuration(self):
        """Read configuration from ``celeryconfig.py`` and configure
        celery and Django so it can be used by regular Python."""
        configname = os.environ.get("CELERY_CONFIG_MODULE",
                                    DEFAULT_CONFIG_MODULE)
        try:
            celeryconfig = self.import_from_cwd(configname)
        except ImportError:
            warnings.warn("No celeryconfig.py module found! Please make "
                          "sure it exists and is available to Python.",
                          NotConfigured)
            return self.setup_settings(DEFAULT_UNCONFIGURED_SETTINGS)
        else:
            usercfg = dict((key, getattr(celeryconfig, key))
                            for key in dir(celeryconfig)
                                if wanted_module_item(key))
            self.configured = True
            return self.setup_settings(usercfg)

    def on_worker_init(self):
        """Imports modules at worker init so tasks can be registered
        and used by the worked.

        The list of modules to import is taken from the ``CELERY_IMPORTS``
        setting in ``celeryconf.py``.

        """
        self.import_default_modules()
