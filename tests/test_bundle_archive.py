"""Exported project bundles are also kept in OMNIVOICE_PROJECT_BUNDLE_DIR."""
import pytest

from services import bundle_archive


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "project.vsproject"
    path.write_bytes(b"zip-bytes")
    return path


def test_off_without_the_env_var(monkeypatch, source):
    monkeypatch.delenv(bundle_archive.ENV_DIR, raising=False)
    assert bundle_archive.archive_copy(source, "My video") is None


def test_copies_with_a_safe_unique_name(monkeypatch, tmp_path, source):
    dest = tmp_path / "workspace" / "projects"
    monkeypatch.setenv(bundle_archive.ENV_DIR, str(dest))
    first = bundle_archive.archive_copy(source, "../../etc/Tanglish: video?", now=0)
    second = bundle_archive.archive_copy(source, "../../etc/Tanglish: video?", now=0)
    assert first.parent == dest and second.parent == dest and first != second
    assert ".." not in first.name and "/" not in first.name and ":" not in first.name
    assert first.read_bytes() == b"zip-bytes" and first.suffix == ".vsproject"


def test_failure_never_raises(monkeypatch, tmp_path, source):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv(bundle_archive.ENV_DIR, str(blocker / "sub"))
    assert bundle_archive.archive_copy(source, "x") is None
    monkeypatch.setenv(bundle_archive.ENV_DIR, str(tmp_path / "ok"))
    assert bundle_archive.archive_copy(tmp_path / "missing", "x") is None
