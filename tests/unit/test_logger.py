"""Unit test for centralized logger."""

from services.common.logger import LOGS_DIR, get_logger


def test_logger_creation_and_file_writing():
    service_name = "test_service"
    logger = get_logger(service_name)
    assert logger.name == f"rag.{service_name}"
    assert len(logger.handlers) >= 2  # Console + global file + service file

    test_msg = "Verification message for structured logger"
    logger.info(test_msg)

    # Check global log file
    global_log = LOGS_DIR / "rag_system.log"
    assert global_log.exists()
    content = global_log.read_text(encoding="utf-8")
    assert test_msg in content

    # Check service specific log file
    service_log = LOGS_DIR / f"{service_name}.log"
    assert service_log.exists()
    service_content = service_log.read_text(encoding="utf-8")
    assert test_msg in service_content
