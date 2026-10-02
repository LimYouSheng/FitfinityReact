"Named, individually reported scenarios for the historical operator regressions."

from functools import partial as bind
from functools import update_wrapper


def partial(function, *args, **kwargs):
    return update_wrapper(bind(function, *args, **kwargs), function)
