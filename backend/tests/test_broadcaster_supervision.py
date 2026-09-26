import asyncio

import pytest

from app.ws.broadcaster import Broadcaster


async def test_run_forever_restarts_after_listen_raises(monkeypatch):
    # #76: listen() dying (a dropped Redis connection, most commonly -- e.g.
    # Redis itself restarting) must not permanently kill live delivery for
    # the whole process. run_forever() has to notice and restart it, not
    # just let the background task disappear silently while everything else
    # (login, REST endpoints) keeps working fine.
    broadcaster = Broadcaster(redis=None, manager=None)
    calls = 0

    async def fake_listen():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("redis went away")
        # Stop the loop once the retry behavior below is proven, rather
        # than looping forever in a test.
        raise asyncio.CancelledError()

    monkeypatch.setattr(broadcaster, "listen", fake_listen)
    sleep_calls = []

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await broadcaster.run_forever()

    assert calls == 3
    # Slept once after each of the first two failures (exponential:
    # 1s, then 2s) -- not after the third, which is the CancelledError
    # that stops the loop before reaching the sleep.
    assert sleep_calls == [1.0, 2.0]


async def test_run_forever_does_not_swallow_cancellation(monkeypatch):
    # A genuine shutdown (the app's own lifespan cancels this task) must
    # propagate immediately, not get treated as just another failure to
    # retry after a backoff.
    broadcaster = Broadcaster(redis=None, manager=None)

    async def fake_listen():
        raise asyncio.CancelledError()

    monkeypatch.setattr(broadcaster, "listen", fake_listen)

    async def fail_if_called(seconds):
        raise AssertionError("should not sleep/retry on cancellation")

    monkeypatch.setattr(asyncio, "sleep", fail_if_called)

    with pytest.raises(asyncio.CancelledError):
        await broadcaster.run_forever()
