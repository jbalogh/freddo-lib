import unittest2 as unittest

import celery


class TestInitFile(unittest.TestCase):

    def test_version(self):
        self.assertTrue(celery.VERSION)
        self.assertGreaterEqual(len(celery.VERSION), 3)
        celery.VERSION = (0, 3, 0)
        self.assertFalse(celery.is_stable_release())
        self.assertGreaterEqual(celery.__version__.count("."), 2)
        self.assertIn("(unstable)", celery.version_with_meta())
        celery.VERSION = (0, 4, 0)
        self.assertTrue(celery.is_stable_release())
        self.assertIn("(stable)", celery.version_with_meta())

    def test_meta(self):
        for m in ("__author__", "__contact__", "__homepage__",
                "__docformat__"):
            self.assertTrue(getattr(celery, m, None))
