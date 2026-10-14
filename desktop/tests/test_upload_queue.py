from dictum.upload_queue import UploadQueue


class FakeBackend:
    def __init__(self, fail_on: str | None = None):
        self.log: list[str] = []
        self.fail_on = fail_on

    def _do(self, what: str):
        if what == self.fail_on:
            raise ConnectionError("offline")
        self.log.append(what)

    def create_recording(self, template, language, recording_id):
        self._do("create")
        return recording_id

    def upload_chunk(self, recording_id, idx, audio, content_type, duration_seconds):
        assert audio == b"OggS..."
        self._do(f"upload{idx}")

    def transcribe_chunk(self, recording_id, idx):
        self._do(f"transcribe{idx}")
        return {}

    def finish(self, recording_id, chunk_count, duration_seconds):
        self._do("finish")
        return {}


def fill(q: UploadQueue):
    q.add_create("r1", "meeting")
    q.add_chunk("r1", 0, b"OggS...", "audio/ogg", 300)
    q.add_chunk("r1", 1, b"OggS...", "audio/ogg", 42)
    q.add_finish("r1", 2, 342)


def test_alles_in_reihenfolge_und_danach_leer(tmp_path):
    q = UploadQueue(tmp_path)
    fill(q)
    backend = FakeBackend()
    assert q.process(backend) == (4, None)
    assert backend.log == ["create", "upload0", "transcribe0", "upload1", "transcribe1", "finish"]
    assert list(tmp_path.iterdir()) == []  # auch die Audio-Dateien sind weg


def test_offline_bleibt_liegen_und_ueberlebt_einen_neustart(tmp_path):
    q = UploadQueue(tmp_path)
    fill(q)
    done, error = q.process(FakeBackend(fail_on="upload1"))
    assert done == 2 and error == "offline"

    # "Neustart": neue Warteschlange auf demselben Ordner
    q2 = UploadQueue(tmp_path)
    backend = FakeBackend()
    q2.process(backend)
    assert backend.log == ["upload1", "transcribe1", "finish"]
