"""Concrete installed transport-to-Reader join; no permission or grant effects."""
from integrations.mastermind_window_reader.broker_window_source import rehydrate
from integrations.mastermind_window_reader.live_window_read import WindowReader, ContentDecision


async def read_installed_window(*, source_ref, access, read_page, now):
    scope=tuple(access['retained_scope'])
    async def page(cursor,max_items):
        return rehydrate(await read_page(access['ticket_digest'],cursor,max_items),expected_scope=scope)
    reader=WindowReader(read_page=page,source_ref=source_ref,expected_scope=scope,
        classify=lambda item:ContentDecision('visible-response',item.text,'VISIBLE_TEXT'),now=now)
    return await reader.read()
