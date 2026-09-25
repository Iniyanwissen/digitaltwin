import uuid
from datetime import UTC, datetime, timedelta

from twin_server.adapters.memory_bus import InMemoryEventBus
from twin_server.adapters.memory_state import InMemoryStateStore
from workplace_domain.enums import EntityType, EventType, IdentityClass, Source, Stream
from workplace_domain.events import EventEnvelope, make_event_id

RUN = uuid.uuid4()


def lifecycle_event(seq: int) -> EventEnvelope:
    t = datetime(2026, 9, 25, 9, 0, tzinfo=UTC) + timedelta(seconds=seq)
    return EventEnvelope(
        event_id=make_event_id(RUN, seq),
        event_type=EventType.SIMULATION_LIFECYCLE,
        event_time=t,
        ingest_time=t,
        source=Source.SIMULATION,
        source_device_id="engine",
        identity_class=IdentityClass.SYSTEM,
        entity_type=EntityType.SIMULATION,
        entity_id=str(RUN),
        building_id="BLD01",
        simulation_run_id=RUN,
        sequence_number=seq,
        payload={"lifecycle": "RUN_STARTED"},
    )


async def test_bus_routes_to_stream_and_preserves_order() -> None:
    bus = InMemoryEventBus(maxlen=10)
    await bus.publish([lifecycle_event(i) for i in range(3)])
    received = await bus.consume([Stream.SYSTEM], max_batch=10, timeout_ms=10)
    assert [r.envelope.sequence_number for r in received] == [0, 1, 2]
    assert all(r.stream is Stream.SYSTEM for r in received)
    assert await bus.consume([Stream.SYSTEM], max_batch=10, timeout_ms=10) == []


async def test_bus_drops_oldest_when_full() -> None:
    bus = InMemoryEventBus(maxlen=2)
    await bus.publish([lifecycle_event(i) for i in range(5)])
    received = await bus.consume([Stream.SYSTEM], max_batch=10, timeout_ms=10)
    assert [r.envelope.sequence_number for r in received] == [3, 4]
    assert (await bus.health()).info["dropped"] == 3


async def test_state_store_hashes_sets_and_prefix_delete() -> None:
    store = InMemoryStateStore()
    await store.set_hash_fields("st:r1:desk:D1", {"sensor_status": "1"})
    await store.set_hash_fields("st:r1:desk:D1", {"sensor_online": "true"})
    await store.add_to_set("st:r1:inside:BLD01", "EMP1", "EMP2")
    await store.remove_from_set("st:r1:inside:BLD01", "EMP1")
    await store.set_hash_fields("st:r2:desk:D1", {"sensor_status": "0"})

    assert await store.get_hash("st:r1:desk:D1") == {"sensor_status": "1", "sensor_online": "true"}
    assert await store.set_members("st:r1:inside:BLD01") == {"EMP2"}
    assert await store.delete_prefix("st:r1:") == 2
    assert await store.get_hash("st:r2:desk:D1") == {"sensor_status": "0"}
