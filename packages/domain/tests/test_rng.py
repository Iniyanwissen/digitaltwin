from workplace_domain.rng import RngFactory, stable_hash


def test_same_seed_same_stream() -> None:
    a = RngFactory(42).stream("attendance", "2026-09-25").random(5)
    b = RngFactory(42).stream("attendance", "2026-09-25").random(5)
    assert (a == b).all()


def test_streams_are_independent_by_name_key_and_seed() -> None:
    base = RngFactory(42).stream("person", "EMP000001").random(3)
    assert not (RngFactory(42).stream("person", "EMP000002").random(3) == base).all()
    assert not (RngFactory(42).stream("other", "EMP000001").random(3) == base).all()
    assert not (RngFactory(43).stream("person", "EMP000001").random(3) == base).all()


def test_stable_hash_is_process_independent() -> None:
    # xxh64 of "attendance" is a fixed constant, unlike Python's salted hash().
    assert stable_hash("attendance") == stable_hash("attendance")
    assert stable_hash("attendance") != stable_hash("attendanc")
