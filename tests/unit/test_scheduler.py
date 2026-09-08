"""Unit test for DirectoryReconciler and SHA-256 deduplication."""

from pathlib import Path

from services.scheduler.reconciler import DirectoryReconciler, compute_file_sha256


def test_sha256_computation(tmp_path: Path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello Hybrid RAG", encoding="utf-8")

    hash1 = compute_file_sha256(test_file)
    hash2 = compute_file_sha256(test_file)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_directory_reconciler_deduplication(tmp_path: Path):
    watch_dir = tmp_path / "documents"
    registry_file = tmp_path / "registry.json"
    watch_dir.mkdir()

    reconciler = DirectoryReconciler(watch_dir=watch_dir, registry_file=registry_file)

    # 1. First scan on empty dir
    new_files = reconciler.reconcile_once()
    assert len(new_files) == 0

    # 2. Add two documents
    doc1 = watch_dir / "doc1.txt"
    doc1.write_text("Document 1 content", encoding="utf-8")
    doc2 = watch_dir / "doc2.txt"
    doc2.write_text("Document 2 content", encoding="utf-8")

    new_files = reconciler.reconcile_once()
    assert len(new_files) == 2
    assert registry_file.exists()

    # 3. Second scan without new files -> should return 0 new files (deduplication)
    new_files_again = reconciler.reconcile_once()
    assert len(new_files_again) == 0

    # 4. Add a third document
    doc3 = watch_dir / "doc3.txt"
    doc3.write_text("Document 3 content", encoding="utf-8")
    new_files_third = reconciler.reconcile_once()
    assert len(new_files_third) == 1
    assert new_files_third[0].name == "doc3.txt"
