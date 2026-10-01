"""Common physical-device requirements for node actions.

A device needs a ``check_status()`` method and either a ``reachable``
attribute or a ``status`` attribute whose connected value is ``"connected"``.
Real wrappers report whether their server (SiLA 2 or SSH) answers in
``reachable``; fakes fall back to their status value.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from madsci.common.types.action_types import ActionFailed


class RequiredDeviceUnavailableError(RuntimeError):
    """Raised when an action's declared physical-device dependency is unavailable."""


def requires_devices(*device_names: str) -> Callable:
    """Declare the fixed devices an action uses before its first physical command.

    The decorated node must provide ``_require_connected_devices(*names)``.
    Failure is converted to the normal MADSci ``ActionFailed`` result before
    the action body runs. ``functools.wraps`` preserves the original action
    signature for MADSci's action schema generation.
    """
    if not device_names or any(not isinstance(name, str) or not name for name in device_names):
        raise ValueError("requires_devices needs one or more non-empty device names")

    def decorate(action_fn: Callable) -> Callable:
        @wraps(action_fn)
        def guarded(self, *args, **kwargs):
            try:
                self._require_connected_devices(*device_names)
            except RequiredDeviceUnavailableError as error:
                return ActionFailed(errors=[error])
            return action_fn(self, *args, **kwargs)

        guarded.required_devices = device_names
        return guarded

    return decorate
