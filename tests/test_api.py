import mock
import unittest

from opentracing.mocktracer import MockTracer
import redis
import redis_opentracing
from redis_opentracing import tracing


class TestGlobalCalls(unittest.TestCase):
    def setUp(self):
        # Stash away the original methods for
        # after-test restoration.
        self._execute_command = redis.StrictRedis.execute_command
        self._pipeline = redis.StrictRedis.pipeline

    def tearDown(self):
        redis.StrictRedis.execute_command = self._execute_command
        redis.StrictRedis.pipeline = self._pipeline
        tracing._reset_tracing()

    def test_init(self):
        tracer = MockTracer()
        redis_opentracing.init_tracing(tracer)
        self.assertEqual(tracer, tracing._g_tracer)
        self.assertEqual(tracer, tracing._get_tracer())
        self.assertEqual(True, tracing._g_trace_all_classes)

    def test_init_subtracer(self):
        tracer = MockTracer()
        tracer._tracer = object()
        redis_opentracing.init_tracing(tracer)
        self.assertEqual(tracer._tracer, tracing._g_tracer)
        self.assertEqual(tracer._tracer, tracing._get_tracer())
        self.assertEqual(True, tracing._g_trace_all_classes)

    def test_init_start_span_cb_invalid(self):
        with self.assertRaises(ValueError):
            redis_opentracing.init_tracing(start_span_cb=1)

    def test_init_start_span_cb(self):
        def start_span_cb(span):
            pass

        redis_opentracing.init_tracing(start_span_cb=start_span_cb)
        self.assertEqual(start_span_cb, tracing._g_start_span_cb)

    def test_init_global_tracer(self):
        with mock.patch('opentracing.tracer') as tracer:
            redis_opentracing.init_tracing()
            self.assertIsNone(tracing._g_tracer)
            self.assertEqual(tracer, tracing._get_tracer())
