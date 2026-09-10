"""Neo4j-backed Knowledge Graph Store for Phase 13 GraphRAG.

Provides native Cypher execution against Neo4j with automatic fallback to
in-memory NetworkX if Neo4j is unavailable or credentials are unconfigured.
Preserves bounding box visual provenance and workspace document scoping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from contracts.chunk import Chunk
from contracts.graph import Entity, GraphNeighborhood, Relation
from services.common.logger import get_logger
from services.graph.extractor import EntityRelationshipExtractor
from services.graph.store import GraphStore as NetworkXGraphStore

logger = get_logger("graph.neo4j_store")


class Neo4jGraphStore:
    """Enterprise Knowledge Graph store powered by Neo4j Cypher queries."""

    def __init__(
        self,
        uri: str = "bolt://127.0.0.1:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
        fallback_store: NetworkXGraphStore | None = None,
        extractor: EntityRelationshipExtractor | None = None,
    ) -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.extractor = extractor or EntityRelationshipExtractor()
        self.fallback = fallback_store or NetworkXGraphStore(extractor=self.extractor)

        self._driver = None
        self._is_connected = False
        self._init_driver()

    def _init_driver(self) -> None:
        """Attempts connection to Neo4j database."""
        try:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            with self._driver.session(database=self.database) as session:
                result = session.run("RETURN 1 AS connected")
                record = result.single()
                if record and record["connected"] == 1:
                    self._is_connected = True
                    self._create_constraints(session)
                    logger.info(f"Connected to Neo4j at {self.uri} (database: {self.database})")
        except Exception as exc:
            self._is_connected = False
            self._driver = None
            logger.info(
                f"Neo4j unavailable at {self.uri} ({exc}). Operating with local NetworkX graph."
            )

    def _create_constraints(self, session: Any) -> None:
        """Ensures uniqueness constraints and indexes exist for high-performance Cypher joins."""
        try:
            session.run(
                "CREATE CONSTRAINT entity_name_unique IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            session.run(
                "CREATE INDEX entity_doc_ids IF NOT EXISTS "
                "FOR (e:Entity) ON (e.doc_ids)"
            )
        except Exception as exc:
            logger.warning(f"Could not create Neo4j constraints/indexes: {exc}")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def add_entity(self, entity: Entity) -> None:
        """Upserts an entity node in Neo4j (or local fallback)."""
        # Always maintain local fallback mirror
        self.fallback.add_entity(entity)

        if not self._is_connected or not self._driver:
            return

        norm_name = entity.name.strip()
        if not norm_name:
            return

        pure_cypher = """
        MERGE (e:Entity {name: $name})
        ON CREATE SET
            e.category = $category,
            e.doc_ids = $doc_ids,
            e.chunk_ids = $chunk_ids,
            e.pages = $pages
        ON MATCH SET
            e.category = CASE WHEN $category <> 'CONCEPT' THEN $category ELSE e.category END
        """

        doc_ids = [entity.doc_id] if entity.doc_id else []
        chunk_ids = [entity.chunk_id] if entity.chunk_id else []
        pages = [entity.page] if entity.page else []

        try:
            with self._driver.session(database=self.database) as session:
                session.run(
                    pure_cypher,
                    name=norm_name,
                    category=entity.category,
                    doc_ids=doc_ids,
                    chunk_ids=chunk_ids,
                    pages=pages,
                )
        except Exception as exc:
            logger.error(f"Failed to add entity to Neo4j: {exc}")

    def add_relation(self, relation: Relation) -> None:
        """Upserts a directional relationship edge between entities in Neo4j."""
        # Always maintain local fallback mirror
        self.fallback.add_relation(relation)

        if not self._is_connected or not self._driver:
            return

        src = relation.source.strip()
        tgt = relation.target.strip()
        if not src or not tgt or src == tgt:
            return

        rel_type = "RELATED_TO"
        sanitized_pred = relation.predicate.replace(" ", "_").upper()
        if sanitized_pred.isalnum():
            rel_type = sanitized_pred

        query = f"""
        MERGE (a:Entity {{name: $src}})
        MERGE (b:Entity {{name: $tgt}})
        MERGE (a)-[r:{rel_type}]->(b)
        SET
            r.predicate = $predicate,
            r.weight = $weight,
            r.doc_id = $doc_id,
            r.chunk_id = $chunk_id,
            r.page = $page,
            r.evidence_snippet = $evidence_snippet
        """

        try:
            with self._driver.session(database=self.database) as session:
                session.run(
                    query,
                    src=src,
                    tgt=tgt,
                    predicate=relation.predicate,
                    weight=relation.weight,
                    doc_id=relation.doc_id,
                    chunk_id=relation.chunk_id,
                    page=relation.page,
                    evidence_snippet=relation.evidence_snippet or "",
                )
        except Exception as exc:
            logger.error(f"Failed to add relation to Neo4j: {exc}")

    def index_chunk(self, chunk: Chunk) -> tuple[int, int]:
        """Extracts entities and relations from a chunk and registers them into Neo4j."""
        res = self.extractor.extract_from_chunk(chunk)
        for e in res.entities:
            self.add_entity(e)
        for r in res.relations:
            self.add_relation(r)
        return len(res.entities), len(res.relations)

    def index_chunks(self, chunks: Sequence[Chunk]) -> tuple[int, int]:
        """Indexes a batch of chunks."""
        total_e = 0
        total_r = 0
        for c in chunks:
            e_cnt, r_cnt = self.index_chunk(c)
            total_e += e_cnt
            total_r += r_cnt
        logger.info(f"Neo4jGraphStore indexed {len(chunks)} chunks -> {total_e} entities, {total_r} relations")
        return total_e, total_r

    def get_neighborhood(self, entity_name: str, max_depth: int = 1) -> GraphNeighborhood:
        """Extracts k-hop neighborhood ego-graph using Cypher variable-length paths."""
        if not self._is_connected or not self._driver:
            return self.fallback.get_neighborhood(entity_name, max_depth=max_depth)

        query = f"""
        MATCH (start:Entity)
        WHERE toLower(start.name) = toLower($name)
        MATCH path = (start)-[r*1..{max_depth}]-(neighbor:Entity)
        UNWIND relationships(path) AS rel
        UNWIND nodes(path) AS node
        RETURN
            collect(DISTINCT node) AS nodes,
            collect(DISTINCT rel) AS rels
        """

        try:
            with self._driver.session(database=self.database) as session:
                res = session.run(query, name=entity_name)
                record = res.single()
                if not record or not record["nodes"]:
                    return self.fallback.get_neighborhood(entity_name, max_depth=max_depth)

                discovered_entities: list[Entity] = []
                chunk_ids: set[str] = set()

                for n in record["nodes"]:
                    discovered_entities.append(
                        Entity(
                            name=n["name"],
                            category=n.get("category", "CONCEPT"),
                            doc_id=(n.get("doc_ids") or [None])[0],
                            chunk_id=(n.get("chunk_ids") or [None])[0],
                            page=(n.get("pages") or [None])[0],
                        )
                    )
                    for cid in n.get("chunk_ids", []):
                        if cid:
                            chunk_ids.add(cid)

                relations: list[Relation] = []
                for r in record["rels"]:
                    relations.append(
                        Relation(
                            source=r.start_node["name"],
                            predicate=r.get("predicate", r.type.lower()),
                            target=r.end_node["name"],
                            doc_id=r.get("doc_id"),
                            chunk_id=r.get("chunk_id"),
                            page=r.get("page"),
                            weight=float(r.get("weight", 1.0)),
                            evidence_snippet=r.get("evidence_snippet"),
                        )
                    )
                    if r.get("chunk_id"):
                        chunk_ids.add(r["chunk_id"])

                return GraphNeighborhood(
                    center_entities=[entity_name],
                    entities=discovered_entities,
                    relations=relations,
                    connected_chunk_ids=sorted(chunk_ids),
                    depth=max_depth,
                )
        except Exception as exc:
            logger.warning(f"Neo4j get_neighborhood failed: {exc}. Falling back to NetworkX.")
            return self.fallback.get_neighborhood(entity_name, max_depth=max_depth)

    def get_connected_chunks(self, entity_names: Sequence[str]) -> list[str]:
        """Returns all chunk IDs connected to any of the provided entity names."""
        if not self._is_connected or not self._driver:
            return self.fallback.get_connected_chunks(entity_names)

        query = """
        MATCH (e:Entity)
        WHERE e.name IN $names
        RETURN collect(e.chunk_ids) AS chunk_arrays
        """
        try:
            with self._driver.session(database=self.database) as session:
                res = session.run(query, names=list(entity_names))
                record = res.single()
                chunk_ids: set[str] = set()
                if record and record["chunk_arrays"]:
                    for arr in record["chunk_arrays"]:
                        if arr:
                            for cid in arr:
                                chunk_ids.add(cid)
                fallback_chunks = self.fallback.get_connected_chunks(entity_names)
                return sorted(chunk_ids.union(fallback_chunks))
        except Exception:
            return self.fallback.get_connected_chunks(entity_names)

    def find_entities_in_text(self, text: str) -> list[Entity]:
        """Finds entities mentioned in text."""
        return self.fallback.find_entities_in_text(text)

    def get_stats(self, doc_ids: Sequence[str] | None = None) -> dict[str, Any]:
        """Returns topological metrics, optionally scoped to specific document IDs."""
        if not self._is_connected or not self._driver:
            stats = self.fallback.get_stats(doc_ids=doc_ids)
            stats["engine"] = "networkx (local)"
            stats["neo4j_connected"] = False
            return stats

        filter_docs = list(doc_ids) if doc_ids is not None else None

        if filter_docs is not None:
            node_query = """
            MATCH (n:Entity)
            WHERE any(d IN n.doc_ids WHERE d IN $doc_ids)
            RETURN count(n) AS node_count, collect(n.category) AS categories
            """
            edge_query = """
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE any(d IN a.doc_ids WHERE d IN $doc_ids) AND any(d IN b.doc_ids WHERE d IN $doc_ids)
            RETURN count(r) AS edge_count, collect(r.predicate) AS predicates
            """
            sample_query = """
            MATCH (n:Entity)
            WHERE any(d IN n.doc_ids WHERE d IN $doc_ids)
            RETURN n.name AS name, n.category AS category, n.doc_ids AS doc_ids
            LIMIT 50
            """
            sample_edge_query = """
            MATCH (a:Entity)-[r]->(b:Entity)
            WHERE any(d IN a.doc_ids WHERE d IN $doc_ids) AND any(d IN b.doc_ids WHERE d IN $doc_ids)
            RETURN a.name AS src, b.name AS tgt, r.predicate AS pred, coalesce(r.weight, 1.0) AS weight, r.doc_id AS doc_id
            LIMIT 50
            """
            params = {"doc_ids": filter_docs}
        else:
            node_query = "MATCH (n:Entity) RETURN count(n) AS node_count, collect(n.category) AS categories"
            edge_query = "MATCH ()-[r]->() RETURN count(r) AS edge_count, collect(r.predicate) AS predicates"
            sample_query = "MATCH (n:Entity) RETURN n.name AS name, n.category AS category, n.doc_ids AS doc_ids LIMIT 50"
            sample_edge_query = "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.name AS src, b.name AS tgt, r.predicate AS pred, coalesce(r.weight, 1.0) AS weight, r.doc_id AS doc_id LIMIT 50"
            params = {}

        try:
            with self._driver.session(database=self.database) as session:
                node_res = session.run(node_query, **params).single()
                edge_res = session.run(edge_query, **params).single()

                num_nodes = node_res["node_count"] if node_res else 0
                num_edges = edge_res["edge_count"] if edge_res else 0

                cat_counts: dict[str, int] = {}
                if node_res and node_res["categories"]:
                    for c in node_res["categories"]:
                        cat = c or "CONCEPT"
                        cat_counts[cat] = cat_counts.get(cat, 0) + 1

                pred_counts: dict[str, int] = {}
                if edge_res and edge_res["predicates"]:
                    for p in edge_res["predicates"]:
                        pred = p or "related_to"
                        pred_counts[pred] = pred_counts.get(pred, 0) + 1

                sample_entities = []
                for rec in session.run(sample_query, **params):
                    sample_entities.append({
                        "name": rec["name"],
                        "category": rec["category"] or "CONCEPT",
                        "doc_ids": rec["doc_ids"] or [],
                    })

                sample_relations = []
                for rec in session.run(sample_edge_query, **params):
                    sample_relations.append({
                        "source": rec["src"],
                        "target": rec["tgt"],
                        "predicate": rec["pred"] or "related_to",
                        "weight": float(rec["weight"]),
                        "doc_id": rec["doc_id"],
                    })

                density = round(num_edges / (num_nodes * (num_nodes - 1)), 4) if num_nodes > 1 else 0.0

                return {
                    "engine": "neo4j",
                    "neo4j_connected": True,
                    "num_nodes": num_nodes,
                    "num_edges": num_edges,
                    "total_entities": num_nodes,
                    "total_relations": num_edges,
                    "total_communities": max(1, len(cat_counts)),
                    "density": density,
                    "entity_categories": cat_counts,
                    "predicates": pred_counts,
                    "sample_entities": sample_entities,
                    "sample_relations": sample_relations,
                }
        except Exception as exc:
            logger.warning(f"Neo4j get_stats failed: {exc}. Falling back to NetworkX.")
            fallback_stats = self.fallback.get_stats(doc_ids=doc_ids)
            fallback_stats["engine"] = "networkx (fallback)"
            fallback_stats["neo4j_connected"] = False
            return fallback_stats

    def clear(self) -> None:
        """Clears graph data from Neo4j and local fallback."""
        self.fallback.clear()
        if self._is_connected and self._driver:
            try:
                with self._driver.session(database=self.database) as session:
                    session.run("MATCH (n) DETACH DELETE n")
            except Exception as exc:
                logger.error(f"Failed to clear Neo4j graph: {exc}")

    def save_to_disk(self, path: Path | str | None = None) -> None:
        """Saves local mirror to disk."""
        self.fallback.save_to_disk(path)

    def load_from_disk(self, path: Path | str | None = None) -> bool:
        """Loads local mirror from disk."""
        return self.fallback.load_from_disk(path)
