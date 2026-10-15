import logging

from multiregistrator.common.logging_setup import get_logger, log_dir, setup_logging


def _flush():
    for handler in logging.getLogger("multiregistrator").handlers:
        handler.flush()


def test_log_dir_default_and_custom(tmp_path):
    assert log_dir(tmp_path) == tmp_path / "logs"


def test_setup_logging_creates_log_file(tmp_path):
    path = setup_logging("unit-logging", base_dir=tmp_path)
    assert path.suffix == ".log"
    assert path.parent == tmp_path / "logs"
    assert path.exists()


def test_get_logger_writes_to_file(tmp_path):
    path = setup_logging("unit-write", base_dir=tmp_path)
    get_logger("testing").warning("hello-log-%s", "world")
    _flush()
    assert "hello-log-world" in path.read_text(encoding="utf-8")


def test_setup_logging_is_idempotent(tmp_path):
    setup_logging("unit-idempotent", base_dir=tmp_path)
    setup_logging("unit-idempotent", base_dir=tmp_path)
    logger = logging.getLogger("multiregistrator")
    target = str((tmp_path / "logs" / "unit-idempotent.log").resolve())
    matches = [h for h in logger.handlers if getattr(h, "baseFilename", None) == target]
    assert len(matches) == 1
