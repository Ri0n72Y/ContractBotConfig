from __future__ import annotations

from typing import Any

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star import star_map, star_registry
from astrbot.core.star.star_handler import star_handlers_registry

from .runtime import ContractFileRouter as RuntimeContractFileRouter


_RUNTIME_MODULE = RuntimeContractFileRouter.__module__


def _remove_runtime_registrations() -> None:
    """Remove registrations created while importing the implementation module.

    AstrBot binds handlers by their exact module path. The implementation class
    lives in runtime.py, but the plugin entrypoint and decorated handlers must
    be registered under main.py. Importing runtime.py creates temporary Star and
    handler records, so remove those records before defining Main below.
    """

    metadata = star_map.pop(_RUNTIME_MODULE, None)
    if metadata is not None and metadata in star_registry:
        star_registry.remove(metadata)

    for handler in list(star_handlers_registry):
        if handler.handler_module_path == _RUNTIME_MODULE:
            star_handlers_registry.remove(handler)


_remove_runtime_registrations()


class Main(RuntimeContractFileRouter):
    """AstrBot Star entrypoint with handlers registered in main.py."""

    @filter.event_message_type(filter.EventMessageType.ALL, priority=1000)
    async def intake(
        self,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ):
        async for result in RuntimeContractFileRouter.intake(
            self,
            event,
            *args,
            **kwargs,
        ):
            yield result

    @filter.on_llm_request(priority=1000)
    async def attach_context(
        self,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ):
        return await RuntimeContractFileRouter.attach_context(
            self,
            event,
            *args,
            **kwargs,
        )

    @filter.after_message_sent(priority=-999)
    async def clear_pending_after_result(
        self,
        event: AstrMessageEvent,
        *args: Any,
        **kwargs: Any,
    ):
        return await RuntimeContractFileRouter.clear_pending_after_result(
            self,
            event,
            *args,
            **kwargs,
        )


__all__ = ["Main"]
