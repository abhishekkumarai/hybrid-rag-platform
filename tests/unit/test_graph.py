"""Unit tests for Phase 13: Graph-Augmented RAG (GraphRAG), Entity Extraction, and Traversal."""

from pathlib import Path

from contracts.chunk import Chunk
from contracts.graph import Entity, Relation
from services.graph.extractor import EntityRelationshipExtractor
from services.graph.store import GraphStore
from services.graph.traversal import GraphTraverser


def test_entity_extractor_recognition():
    extractor = EntityRelationshipExtractor()
    text = (
        "The NVIDIA RTX 3050 Laptop GPU has 6GB VRAM and runs on CPU with FlashRank. "
        "It indexes into Qdrant vector database and BM25s lexical index."
    )
    entities = extractor.extract_entities(text, doc_id="doc1", chunk_id="c1", page=1, bbox=(0, 0, 100, 100))

    names = {e.name for e in entities}
    assert "NVIDIA RTX 3050" in names
    assert "VRAM" in names or "6GB" in names
    assert "FlashRank" in names
    assert "Qdrant" in names
    assert "BM25s" in names

    # Check preserved coordinates
    for e in entities:
        assert e.doc_id == "doc1"
        assert e.chunk_id == "c1"
        assert e.page == 1
        assert e.bbox == (0, 0, 100, 100)


def test_relation_extractor_patterns():
    extractor = EntityRelationshipExtractor()
    text = "FlashRank runs on CPU for fast cross-encoder reranking. The system indexes into Qdrant."
    relations = extractor.extract_relations(text, doc_id="doc1", chunk_id="c1")

    assert len(relations) >= 1
    # Check that FlashRank runs on CPU or system indexes into Qdrant is extracted
    predicates = [r.predicate for r in relations]
    assert any(p in ["runs_on", "indexes_into", "associated_with"] for p in predicates)

    # Check evidence snippet
    for r in relations:
        assert r.doc_id == "doc1"
        assert r.chunk_id == "c1"
        assert r.evidence_snippet is not None


def test_graph_store_add_and_neighborhood(tmp_path: Path):
    store = GraphStore(persistence_path=tmp_path / "test_kg.json", auto_load=False)

    e1 = Entity(name="NVIDIA RTX 3050", category="HARDWARE", doc_id="doc_a", chunk_id="ca1", page=1)
    e2 = Entity(name="6GB VRAM", category="METRIC", doc_id="doc_a", chunk_id="ca1", page=1)
    e3 = Entity(name="Llama 3.2", category="SOFTWARE", doc_id="doc_b", chunk_id="cb1", page=2)

    store.add_entity(e1)
    store.add_entity(e2)
    store.add_entity(e3)

    r1 = Relation(source="NVIDIA RTX 3050", predicate="has_memory", target="6GB VRAM", doc_id="doc_a", chunk_id="ca1")
    r2 = Relation(source="Llama 3.2", predicate="runs_on", target="NVIDIA RTX 3050", doc_id="doc_b", chunk_id="cb1")

    store.add_relation(r1)
    store.add_relation(r2)

    # Test neighborhood
    nb = store.get_neighborhood("NVIDIA RTX 3050", max_depth=1)
    assert nb.center_entities == ["NVIDIA RTX 3050"]
    nb_names = {e.name for e in nb.entities}
    assert "NVIDIA RTX 3050" in nb_names
    assert "6GB VRAM" in nb_names
    assert "Llama 3.2" in nb_names
    assert len(nb.relations) == 2
    assert "ca1" in nb.connected_chunk_ids
    assert "cb1" in nb.connected_chunk_ids


def test_graph_store_persistence(tmp_path: Path):
    save_file = tmp_path / "graph.json"
    store1 = GraphStore(persistence_path=save_file, auto_load=False)

    chunk = Chunk(
        id="c100",
        doc_id="arch_spec",
        page=1,
        page_end=1,
        bbox=(10.0, 10.0, 200.0, 50.0),
        text="Qdrant provides HNSW vector search, and BM25s provides sparse search.",
        raw_text="Qdrant provides HNSW vector search, and BM25s provides sparse search.",
        token_count=15,
    )
    store1.index_chunk(chunk)
    store1.save_to_disk()
    assert save_file.exists()

    # Load in fresh store
    store2 = GraphStore(persistence_path=save_file, auto_load=True)
    stats = store2.get_stats()
    assert stats["num_nodes"] >= 2
    assert store2.get_entity("Qdrant") is not None


def test_graph_traverser_associative_path():
    store = GraphStore(auto_load=False)

    # Multi-hop associative connection across docs:
    # Doc 1: Abhishek worked at Syngene
    # Doc 2: Syngene collaborated with Bristol Myers Squibb
    # Traverser discovers: Abhishek -> Syngene -> Bristol Myers Squibb
    store.add_relation(Relation(source="Abhishek", predicate="worked_at", target="Syngene", doc_id="doc1", chunk_id="c1"))
    store.add_relation(Relation(source="Syngene", predicate="partnered_with", target="Bristol Myers Squibb", doc_id="doc2", chunk_id="c2"))

    traverser = GraphTraverser(store)
    path = traverser.find_associative_path("Abhishek", "Bristol Myers Squibb")
    assert path == ["Abhishek", "Syngene", "Bristol Myers Squibb"]

    # Test full traversal query
    response = traverser.query_graph("How is Abhishek connected to Bristol Myers Squibb?")
    assert len(response.matched_entities) >= 1
    assert len(response.relations) >= 1
    assert "Syngene" in response.subgraph_text
    assert "c1" in response.connected_chunk_ids or "c2" in response.connected_chunk_ids
