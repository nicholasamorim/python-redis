from functools import wraps

import redis

g_tracer = None
g_trace_prefix = None
g_trace_all_classes = True

def init_tracing(tracer, trace_all_classes=True, prefix='Redis'):
    global g_tracer, g_trace_all_classes, g_trace_prefix
    if hasattr(tracer, '_tracer'):
        tracer = tracer._tracer

    g_tracer = tracer
    g_trace_all_classes = trace_all_classes
    g_trace_prefix = prefix

    if g_trace_all_classes:
        _patch_redis_classes()

def trace_client(client):
    _patch_client(client)

def trace_pipeline(pipe):
    _patch_pipe_execute(pipe)

def _get_operation_name(operation_name):
    if g_trace_prefix is not None:
        operation_name = '{0}/{1}'.format(g_trace_prefix, operation_name)

    return operation_name

def _normalize_stmt(args):
    return ' '.join([str(arg) for arg in args])

def _normalize_stmts(command_stack):
    commands = [_normalize_stmt(command[0]) for command in command_stack]
    return ';'.join(commands)

def _set_base_span_tags(span, stmt):
    span.set_tag('component', 'redis-py')
    span.set_tag('db.type', 'redis')
    span.set_tag('db.statement', stmt)
    span.set_tag('span.kind', 'client')


def _patch_redis_classes():
    # Patch the outgoing commands.
    _patch_obj_execute_command(redis.StrictRedis, True)
    
    # Patch the created pipelines.
    pipeline_method = redis.StrictRedis.pipeline

    @wraps(pipeline_method)
    def tracing_pipeline(self, transaction=True, shard_hint=None):
        pipe = pipeline_method(self, transaction, shard_hint)
        _patch_pipe_execute(pipe)
        return pipe

    redis.StrictRedis.pipeline = tracing_pipeline


def _patch_client(client):
    # Patch the outgoing commands.
    _patch_obj_execute_command(client)

    # Patch the created pipelines.
    pipeline_method = client.pipeline

    @wraps(pipeline_method)
    def tracing_pipeline(self, transaction=True, shard_hint=None):
        pipe = pipeline_method(transaction, shard_hint)
        _patch_pipe_execute(pipe)
        return pipe

    client.pipeline = tracing_pipeline


def _patch_pipe_execute(pipe):
    execute_method = pipe.execute

    @wraps(execute_method)
    def tracing_execute(raise_on_error=True):
        span = g_tracer.start_span(_get_operation_name('MULTI'))
        _set_base_span_tags(span, _normalize_stmts(pipe.command_stack))

        try:
            res = execute_method(raise_on_error=raise_on_error)
        except Exception as exc:
            span.set_tag('error', 'true')
            span.set_tag('error.object', exc)
            raise
        finally:
            span.finish()

        return res

    pipe.execute = tracing_execute


def _patch_obj_execute_command(redis_obj, is_klass=False):
    execute_command_method = redis_obj.execute_command

    @wraps(execute_command_method)
    def tracing_execute_command(*args, **kwargs):
        if is_klass: 
            # Unbound method, we will get 'self' in args.
            reported_args = args[1:]
        else:
            reported_args = args

        command = reported_args[0]

        span = g_tracer.start_span(_get_operation_name(command))
        _set_base_span_tags(span, _normalize_stmt(reported_args))

        try:
            rv = execute_command_method(*args, **kwargs)
        except Exception as exc:
            span.set_tag('error', 'true')
            span.set_tag('error.object', exc)
            raise
        finally:
            span.finish()

        return rv

    redis_obj.execute_command = tracing_execute_command