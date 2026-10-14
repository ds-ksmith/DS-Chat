import os
import time
import uuid

import pytest_asyncio
from redis.asyncio import Redis

from app.schemas.room import RoomCreate
from app.schemas.user import UserCreate
from app.services.auth_service import register_user
from app.services.room_service import create_room, find_or_create_dm
from app.ws.expiring_presence import ExpiringPresenceSet
from app.ws.global_presence import GlobalPresence
from app.ws.presence_sweeper import SWEEP_LOCK_KEY, purge_legacy_presence, sweep_once


class Clock:
    def __init__(self) -> None:
        self.now = time.time()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeBroadcaster:
    def __init__(self) -> None:
        self.room_events: list[tuple[uuid.UUID, dict]] = []
        self.user_events: list[tuple[uuid.UUID, dict]] = []

    async def publish(self, room_id, payload):
        self.room_events.append((room_id, payload))

    async def publish_to_user(self, user_id, payload):
        self.user_events.append((user_id, payload))


@pytest_asyncio.fixture
async def redis_client():
    client = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    await client.delete(GlobalPresence.KEY, SWEEP_LOCK_KEY)
    yield client
    await client.delete(GlobalPresence.KEY, SWEEP_LOCK_KEY)
    await client.aclose()


@pytest_asyncio.fixture
async def world(redis_client, db_session):
    clock = Clock()
    presence = GlobalPresence(redis_client, ExpiringPresenceSet(redis_client, ttl_seconds=90, clock=clock))
    broadcaster = FakeBroadcaster()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *exc):
            return False

    async def make_user(prefix: str):
        name = f"{prefix}-{uuid.uuid4().hex[:8]}"
        return await register_user(
            db_session, UserCreate(username=name, email=f"{name}@example.com", password="password123")
        )

    async def sweep(**kwargs):
        return await sweep_once(redis_client, presence, broadcaster, _Factory(), **kwargs)

    return clock, presence, broadcaster, make_user, sweep


async def test_sweep_announces_a_user_whose_connection_expired(world, db_session):
    clock, presence, broadcaster, make_user, sweep = world
    alice, bob = await make_user("alice"), await make_user("bob")
    room = await create_room(db_session, alice.id, RoomCreate(name=f"r-{uuid.uuid4().hex[:8]}"))
    dm = await find_or_create_dm(db_session, alice.id, bob.id)

    await presence.connect(alice.id, "tab1")
    clock.advance(200)

    assert await sweep(lock_seconds=None) == {alice.id}

    room_ids = {rid for rid, p in broadcaster.room_events if p["type"] == "member_updated"}
    assert {room.id, dm.id} <= room_ids
    assert (bob.id, {"type": "dm_presence_update", "user_id": str(alice.id), "status": "offline"}) in (
        broadcaster.user_events
    )
    assert await presence.is_online(alice.id) is False


async def test_sweep_announces_each_expiry_only_once(world, db_session):
    clock, presence, broadcaster, make_user, sweep = world
    alice = await make_user("alice")
    await create_room(db_session, alice.id, RoomCreate(name=f"r-{uuid.uuid4().hex[:8]}"))
    await presence.connect(alice.id, "tab1")
    clock.advance(200)

    await sweep(lock_seconds=None)
    sent = len(broadcaster.room_events)
    assert sent > 0
    assert await sweep(lock_seconds=None) == set()
    assert len(broadcaster.room_events) == sent


async def test_sweep_stays_quiet_while_the_user_has_another_live_connection(world, db_session):
    clock, presence, broadcaster, make_user, sweep = world
    alice = await make_user("alice")
    await create_room(db_session, alice.id, RoomCreate(name=f"r-{uuid.uuid4().hex[:8]}"))
    await presence.connect(alice.id, "old-tab")
    clock.advance(60)
    await presence.connect(alice.id, "new-tab")
    clock.advance(60)

    assert await sweep(lock_seconds=None) == set()
    assert broadcaster.room_events == []
    assert await presence.is_online(alice.id) is True


async def test_sweep_leaves_healthy_connections_alone(world, db_session):
    clock, presence, broadcaster, make_user, sweep = world
    alice = await make_user("alice")
    await presence.connect(alice.id, "tab1")
    clock.advance(30)
    assert await sweep(lock_seconds=None) == set()
    assert broadcaster.room_events == []


async def test_only_one_sweeper_runs_per_interval(world, db_session, redis_client):
    clock, presence, broadcaster, make_user, sweep = world
    alice = await make_user("alice")
    await presence.connect(alice.id, "tab1")
    clock.advance(200)

    # Another worker holds the lock: this one must not sweep (or broadcast).
    await redis_client.set(SWEEP_LOCK_KEY, "1", ex=14)
    assert await sweep(lock_seconds=14) == set()
    assert await redis_client.zcard(GlobalPresence.KEY) == 1

    await redis_client.delete(SWEEP_LOCK_KEY)
    assert await sweep(lock_seconds=14) == {alice.id}
    # And the lock is now held, so an immediate second attempt does nothing.
    assert await sweep(lock_seconds=14) == set()


async def test_one_failed_broadcast_does_not_stop_the_rest(world, db_session):
    clock, presence, broadcaster, make_user, sweep = world
    alice, bob = await make_user("alice"), await make_user("bob")
    room = await create_room(db_session, alice.id, RoomCreate(name=f"r-{uuid.uuid4().hex[:8]}"))
    other = await create_room(db_session, bob.id, RoomCreate(name=f"r-{uuid.uuid4().hex[:8]}"))
    await presence.connect(alice.id, "a")
    await presence.connect(bob.id, "b")
    clock.advance(200)

    real_publish = broadcaster.publish
    failed = []

    async def flaky_publish(room_id, payload):
        if room_id == room.id:
            failed.append(room_id)
            raise RuntimeError("redis hiccup")
        await real_publish(room_id, payload)

    broadcaster.publish = flaky_publish

    assert await sweep(lock_seconds=None) == {alice.id, bob.id}
    assert failed == [room.id]
    assert other.id in {rid for rid, _ in broadcaster.room_events}


async def test_purge_removes_legacy_keys_but_keeps_v2(redis_client):
    legacy = ["presence:global", "presence:unfocused", f"presence:{uuid.uuid4()}"]
    current = f"presence:v2:test:{uuid.uuid4()}"
    for key in legacy:
        await redis_client.hset(key, "someone", 3)
    await redis_client.zadd(current, {"x:y": time.time() + 90})

    try:
        assert await purge_legacy_presence(redis_client) >= len(legacy)
        for key in legacy:
            assert await redis_client.exists(key) == 0
        assert await redis_client.exists(current) == 1
    finally:
        await redis_client.delete(current, *legacy)
