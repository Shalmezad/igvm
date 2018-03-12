"""igvm - Transaction System

Copyright (c) 2018, InnoGames GmbH
"""

import logging

log = logging.getLogger(__name__)


class Transaction(object):
    """Context manager of an igvm action with rollback support

    Each successful step register a callback to undo its changes.
    If the transaction fails, all registered callbacks are invoked in
    LIFO order.
    """
    def __init__(self):
        self._actions = None

    def __enter__(self):
        self._actions = []

        return self

    def __exit__(self, type, value, traceback):
        if traceback:
            self.rollback()

        self._actions = None    # Invalidate transaction

    def on_rollback(self, name, fn, *args, **kwargs):
        assert callable(fn)

        self._actions.append((name, fn, args, kwargs))

    def rollback(self):
        log.info('Rolling back transaction')
        for name, fn, args, kwargs in reversed(self._actions):
            log.debug('Running rollback action "{}"'.format(name))

            try:
                fn(*args, **kwargs)
            except Exception as exception:
                log.warning(
                    'Rollback action "{}" failed: {}'.format(name, exception)
                )
