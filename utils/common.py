import functools

def auto_endpoint(bp_or_app):
    def route_wrapper(rule, **options):
        def decorator(f):
            endpoint = options.get('endpoint') or f.__name__.replace('_', '-')
            options['endpoint'] = endpoint
            return bp_or_app.route(rule, **options)(f)
        return decorator
    return route_wrapper