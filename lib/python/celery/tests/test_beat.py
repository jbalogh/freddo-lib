import logging
import unittest2 as unittest
from datetime import datetime, timedelta

from celery import log
from celery import beat
from celery import conf
from celery.utils import gen_unique_id
from celery.task.base import PeriodicTask
from celery.registry import TaskRegistry
from celery.result import AsyncResult


class MockShelve(dict):
    closed = False
    synced = False

    def close(self):
        self.closed = True

    def sync(self):
        self.synced = True


class MockClockService(object):
    started = False
    stopped = False

    def __init__(self, *args, **kwargs):
        pass

    def start(self, **kwargs):
        self.started = True

    def stop(self, **kwargs):
        self.stopped = True


class DuePeriodicTask(PeriodicTask):
    run_every = timedelta(seconds=1)
    applied = False

    def is_due(self, *args, **kwargs):
        return True, 100

    @classmethod
    def apply_async(self, *args, **kwargs):
        self.applied = True
        return AsyncResult(gen_unique_id())


class DuePeriodicTaskRaising(PeriodicTask):
    run_every = timedelta(seconds=1)
    applied = False

    def is_due(self, *args, **kwargs):
        return True, 0

    @classmethod
    def apply_async(self, *args, **kwargs):
        raise Exception("FoozBaaz")


class PendingPeriodicTask(PeriodicTask):
    run_every = timedelta(seconds=1)
    applied = False

    def is_due(self, *args, **kwargs):
        return False, 100

    @classmethod
    def apply_async(self, *args, **kwargs):
        self.applied = True
        return AsyncResult(gen_unique_id())


class AdditionalTask(PeriodicTask):
    run_every = timedelta(days=7)

    @classmethod
    def apply_async(self, *args, **kwargs):
        raise Exception("FoozBaaz")


class TestScheduleEntry(unittest.TestCase):

    def test_constructor(self):
        s = beat.ScheduleEntry(DuePeriodicTask.name)
        self.assertEqual(s.name, DuePeriodicTask.name)
        self.assertIsInstance(s.last_run_at, datetime)
        self.assertEqual(s.total_run_count, 0)

        now = datetime.now()
        s = beat.ScheduleEntry(DuePeriodicTask.name, now, 300)
        self.assertEqual(s.name, DuePeriodicTask.name)
        self.assertEqual(s.last_run_at, now)
        self.assertEqual(s.total_run_count, 300)

    def test_next(self):
        s = beat.ScheduleEntry(DuePeriodicTask.name, None, 300)
        n = s.next()
        self.assertEqual(n.name, s.name)
        self.assertEqual(n.total_run_count, 301)
        self.assertGreater(n.last_run_at, s.last_run_at)

    def test_is_due(self):
        due = beat.ScheduleEntry(DuePeriodicTask.name)
        pending = beat.ScheduleEntry(PendingPeriodicTask.name)

        self.assertTrue(due.is_due(DuePeriodicTask())[0])
        self.assertFalse(pending.is_due(PendingPeriodicTask())[0])


class TestScheduler(unittest.TestCase):

    def setUp(self):
        self.registry = TaskRegistry()
        self.registry.register(DuePeriodicTask)
        self.registry.register(PendingPeriodicTask)
        self.scheduler = beat.Scheduler(self.registry,
                                        max_interval=0.0001,
                                        logger=log.get_default_logger())

    def test_constructor(self):
        s = beat.Scheduler()
        self.assertIsInstance(s.registry, TaskRegistry)
        self.assertIsInstance(s.schedule, dict)
        self.assertIsInstance(s.logger, logging.Logger)
        self.assertEqual(s.max_interval, conf.CELERYBEAT_MAX_LOOP_INTERVAL)

    def test_cleanup(self):
        self.scheduler.schedule["fbz"] = beat.ScheduleEntry("fbz")
        self.scheduler.cleanup()
        self.assertNotIn("fbz", self.scheduler.schedule)

    def test_schedule_registry(self):
        self.registry.register(AdditionalTask)
        self.scheduler.schedule_registry()
        self.assertIn(AdditionalTask.name, self.scheduler.schedule)

    def test_apply_async(self):
        due_task = self.registry[DuePeriodicTask.name]
        self.scheduler.apply_async(self.scheduler[due_task.name])
        self.assertTrue(due_task.applied)

    def test_apply_async_raises_SchedulingError_on_error(self):
        self.registry.register(AdditionalTask)
        self.scheduler.schedule_registry()
        add_task = self.registry[AdditionalTask.name]
        self.assertRaises(beat.SchedulingError,
                          self.scheduler.apply_async,
                          self.scheduler[add_task.name])

    def test_is_due(self):
        due = self.scheduler[DuePeriodicTask.name]
        pending = self.scheduler[PendingPeriodicTask.name]

        self.assertTrue(self.scheduler.is_due(due)[0])
        self.assertFalse(self.scheduler.is_due(pending)[0])

    def test_tick(self):
        self.scheduler.schedule.pop(DuePeriodicTaskRaising.name, None)
        self.registry.pop(DuePeriodicTaskRaising.name, None)
        self.assertEqual(self.scheduler.tick(),
                            self.scheduler.max_interval)

    def test_quick_schedulingerror(self):
        self.registry.register(DuePeriodicTaskRaising)
        self.scheduler.schedule_registry()
        self.assertEqual(self.scheduler.tick(),
                            self.scheduler.max_interval)


class TestClockService(unittest.TestCase):

    def test_start(self):
        s = beat.ClockService()
        sh = MockShelve()
        s.open_schedule = lambda *a, **kw: sh

        self.assertIsInstance(s.schedule, dict)
        self.assertIsInstance(s.schedule, dict)
        self.assertIsInstance(s.scheduler, beat.Scheduler)
        self.assertIsInstance(s.scheduler, beat.Scheduler)

        self.assertIs(s.schedule, sh)
        self.assertIs(s._schedule, sh)

        s._in_sync = False
        s.sync()
        self.assertTrue(sh.closed)
        self.assertTrue(sh.synced)
        self.assertTrue(s._stopped.isSet())
        s.sync()

        s.stop(wait=False)
        self.assertTrue(s._shutdown.isSet())
        s.stop(wait=True)
        self.assertTrue(s._shutdown.isSet())


class TestEmbeddedClockService(unittest.TestCase):

    def test_start_stop_process(self):
        s = beat.EmbeddedClockService()
        from multiprocessing import Process
        self.assertIsInstance(s, Process)
        self.assertIsInstance(s.clockservice, beat.ClockService)
        s.clockservice = MockClockService()

        class _Popen(object):
            terminated = False

            def terminate(self):
                self.terminated = True

        s.run()
        self.assertTrue(s.clockservice.started)

        s._popen = _Popen()
        s.stop()
        self.assertTrue(s.clockservice.stopped)
        self.assertTrue(s._popen.terminated)

    def test_start_stop_threaded(self):
        s = beat.EmbeddedClockService(thread=True)
        from threading import Thread
        self.assertIsInstance(s, Thread)
        self.assertIsInstance(s.clockservice, beat.ClockService)
        s.clockservice = MockClockService()

        s.run()
        self.assertTrue(s.clockservice.started)

        s.stop()
        self.assertTrue(s.clockservice.stopped)
