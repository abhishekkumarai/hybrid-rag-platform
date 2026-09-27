"""Unit tests for the shared project document-scope matcher (IRA-6)."""

from services.common.doc_scope import matches_doc_scope, normalize_doc_id


def test_normalize_doc_id():
    assert normalize_doc_id("Report 2024.PDF") == "report_2024"
    assert normalize_doc_id("system-architecture-spec") == "system_architecture_spec"


def test_exact_and_filename_forms_match_hashed_id():
    hashed = "system_architecture_spec_81b5f5cd"
    assert matches_doc_scope(hashed, {hashed})
    assert matches_doc_scope(hashed, {"system_architecture_spec"})
    assert matches_doc_scope(hashed, {"system_architecture_spec.pdf"})
    assert matches_doc_scope(hashed, {"System Architecture Spec.pdf"})
    assert matches_doc_scope("alpha_report.pdf", {"alpha_report.pdf"})


def test_sibling_documents_do_not_leak_via_prefix():
    assert not matches_doc_scope("report_final_ab12cd34", {"report.pdf"})
    assert not matches_doc_scope("report_ab12cd34", {"report_final.pdf"})
    assert not matches_doc_scope("report", {"report_final_ab12cd34"})
    # A different content hash of the same stem is a different document version.
    assert not matches_doc_scope("report_ab12cd34", {"report_99999999"})


def test_empty_candidate_never_matches():
    assert not matches_doc_scope(None, {"a"})
    assert not matches_doc_scope("", {"a"})
