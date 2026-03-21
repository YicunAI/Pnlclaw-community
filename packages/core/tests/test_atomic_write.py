"""Tests for pnlclaw_core.infra.atomic_write."""


from pnlclaw_core.infra.atomic_write import atomic_write


class TestAtomicWrite:
    def test_write_text(self, tmp_path):
        target = tmp_path / "test.txt"
        atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_write_bytes(self, tmp_path):
        target = tmp_path / "test.bin"
        atomic_write(target, b"\x00\x01\x02")
        assert target.read_bytes() == b"\x00\x01\x02"

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir" / "file.txt"
        atomic_write(target, "nested")
        assert target.read_text() == "nested"

    def test_overwrites_existing(self, tmp_path):
        target = tmp_path / "test.txt"
        target.write_text("old content")
        atomic_write(target, "new content")
        assert target.read_text() == "new content"

    def test_no_leftover_tmp_on_success(self, tmp_path):
        target = tmp_path / "test.txt"
        atomic_write(target, "content")
        tmp_files = list(tmp_path.glob(".*tmp"))
        assert len(tmp_files) == 0

    def test_original_intact_on_error(self, tmp_path):
        """If writing fails, the original file should remain intact."""
        target = tmp_path / "test.txt"
        target.write_text("original")

        # Simulate a write failure by passing a bad type
        try:
            atomic_write(target, 12345)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            pass

        assert target.read_text() == "original"
