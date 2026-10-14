import os
import time
import uuid

import pytest_asyncio
from redis.asyncio import Redis

from app.ws.expiring_presence import ExpiringPresenceSet


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest_asyncio.fixture
async def redis_client():
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def setup(redis_client):
    clock = Clock()
    store = ExpiringPresenceSet(redis_client, ttl_seconds=90, clock=clock)
    key = f"presence:v2:test:{uuid.uuid4()}"
    yield store, clock, key
    await redis_client.delete(key)


async def test_first_connection_is_a_transition_and_a_second_is_not(setup):
    store, _, key = setup
    user = uuid.uuid4()
    assert await store.add(key, user, "tab1") is True
    assert await store.add(key, user, "tab2") is False
    assert await store.live_user_ids(key) == {user}


async def test_renewing_a_live_entry_is_not_a_transition(setup):
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    clock.advance(30)
    assert await store.add(key, user, "tab1") is False


async def test_entry_stops_counting_after_the_ttl(setup):
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    clock.advance(89)
    assert await store.is_live(key, user) is True
    clock.advance(2)
    assert await store.is_live(key, user) is False
    assert await store.live_user_ids(key) == set()


async def test_renewal_keeps_a_connection_alive_past_the_original_expiry(setup):
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    for _ in range(5):
        clock.advance(60)
        await store.add(key, user, "tab1")
    assert await store.is_live(key, user) is True


async def test_coming_back_after_expiry_is_a_transition_again(setup):
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    clock.advance(200)
    assert await store.add(key, user, "tab1") is True


async def test_one_live_connection_keeps_the_user_online_when_another_expires(setup):
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "old-tab")
    clock.advance(60)
    await store.add(key, user, "new-tab")
    clock.advance(60)  # old-tab is now 120s stale, new-tab 60s
    assert await store.is_live(key, user) is True


async def test_remove_reports_only_the_last_connection_leaving(setup):
    store, _, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    await store.add(key, user, "tab2")
    assert await store.remove(key, user, "tab1") is False
    assert await store.remove(key, user, "tab2") is True


async def test_remove_of_an_entry_that_is_already_gone_reports_nothing(setup):
    # Whoever removed it first (e.g. prune) already reported the transition.
    store, _, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    await store.remove(key, user, "tab1")
    assert await store.remove(key, user, "tab1") is False


async def test_remove_of_an_expired_but_unpruned_entry_still_reports_offline(setup):
    # Nobody has been told this user went offline yet (no prune has run), so
    # their eventual clean close is the one place left to report it.
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    clock.advance(200)
    assert await store.remove(key, user, "tab1") is True


async def test_users_are_independent(setup):
    store, _, key = setup
    alice, bob = uuid.uuid4(), uuid.uuid4()
    await store.add(key, alice, "a")
    await store.add(key, bob, "b")
    await store.remove(key, alice, "a")
    assert await store.live_user_ids(key) == {bob}


async def test_prune_reports_users_who_lost_their_last_live_entry(setup):
    store, clock, key = setup
    gone, still_here = uuid.uuid4(), uuid.uuid4()
    await store.add(key, gone, "tab1")
    await store.add(key, still_here, "old")
    clock.advance(60)
    await store.add(key, still_here, "new")
    clock.advance(40)  # gone/tab1 and still_here/old are expired; still_here/new is not
    assert await store.prune(key) == {gone}


async def test_prune_is_idempotent_and_removes_what_it_reports(setup):
    store, clock, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    clock.advance(200)
    assert await store.prune(key) == {user}
    assert await store.prune(key) == set()


async def test_prune_with_nothing_expired_does_nothing(setup):
    store, _, key = setup
    user = uuid.uuid4()
    await store.add(key, user, "tab1")
    assert await store.prune(key) == set()
    assert await store.is_live(key, user) is True
