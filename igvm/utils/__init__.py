"""igvm -  Utilities

Copyright (c) 2018, InnoGames GmbH
"""
# XXX: This module is deprecated.  New modules should go to top level "igvm"
# module.

import os
from pipes import quote

import igvm


def get_installdir():
    return os.path.dirname(igvm.__file__)


def cmd(cmd, *args, **kwargs):
    escaped_args = [quote(str(arg)) for arg in args]

    escaped_kwargs = {}
    for key, value in kwargs.iteritems():
        escaped_kwargs[key] = quote(str(value))

    return cmd.format(*escaped_args, **escaped_kwargs)
