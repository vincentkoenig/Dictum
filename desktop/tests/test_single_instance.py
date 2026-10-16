import uuid

from dictum.single_instance import SingleInstance


def unique_name() -> str:
    # Jeder Test bekommt einen eigenen Namen, damit er nicht mit einem laufenden Dictum
    # (oder einem anderen Test) kollidiert
    return f"Local\\DictumTest-{uuid.uuid4()}"


def test_zweiter_start_erkennt_den_ersten():
    name = unique_name()
    first = SingleInstance(name)
    second = SingleInstance(name)
    try:
        assert first.already_running is False
        assert second.already_running is True
    finally:
        first.release()
        second.release()


def test_nach_dem_beenden_darf_wieder_gestartet_werden():
    name = unique_name()
    first = SingleInstance(name)
    first.release()  # wie ein beendeter Prozess
    again = SingleInstance(name)
    try:
        assert again.already_running is False
    finally:
        again.release()


def test_verschiedene_namen_stoeren_sich_nicht():
    a, b = SingleInstance(unique_name()), SingleInstance(unique_name())
    try:
        assert not a.already_running and not b.already_running
    finally:
        a.release()
        b.release()
