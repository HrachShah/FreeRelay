"""Compatibility helpers for stdlib features across supported runtimes."""

from __future__ import annotations

import sys
from enum import Enum

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    class StrEnum(str, Enum):
        """Backport of Python 3.11's StrEnum for older runtimes."""
