"""Minimal Streamlit compatibility layer for local maintenance scripts.

Loader modules use only cache decorators and optional secrets. Importing the full
Streamlit runtime inside a maintenance command adds noise and state that the
command does not need, so a script may install this module before importing
loaders.
"""

from __future__ import annotations

import sys
import types


class _CacheDecorator:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def clear(self) -> None:
        return None


class _StreamlitStub(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("streamlit")
        self.cache_data = _CacheDecorator()
        self.cache_resource = _CacheDecorator()
        self.secrets = {}
        self.session_state = {}


def install_streamlit_stub() -> None:
    existing = sys.modules.get("streamlit")
    if existing is None or isinstance(existing, _StreamlitStub):
        sys.modules["streamlit"] = _StreamlitStub()
