"""Metadata identity of the explicitly environment-bound central SPF config.

No configuration contents or credentials are read. This is an invalidation
hint, not the age/version of the underlying geographical datasets.
"""

import os
from pathlib import Path


def area_source_identity() -> tuple:
    value = os.environ.get('STARGAZING_CONFIG')
    if not value:
        return (None,)
    path = Path(value).absolute()
    try:
        info = path.stat()
        stamp = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    except FileNotFoundError:
        stamp = ('missing',)
    return (str(path), stamp)
