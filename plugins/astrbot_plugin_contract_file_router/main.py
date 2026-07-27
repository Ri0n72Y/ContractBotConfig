from __future__ import annotations

from .runtime import ContractFileRouter as RuntimeContractFileRouter


class Main(RuntimeContractFileRouter):
    """AstrBot Star entrypoint defined in main.py.

    The runtime implementation remains in runtime.py, while this concrete
    subclass ensures AstrBot's plugin loader discovers and registers the Star.
    """


__all__ = ["Main"]
