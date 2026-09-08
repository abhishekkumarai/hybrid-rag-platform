"""Local Knowledge Graph Store backed by NetworkX for Phase 13 GraphRAG.

Provides in-memory graph operations, node/edge indexing with preserved document provenance,
subgraph extraction, and JSON disk persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import networkx as nx

from contracts.chunk import Chunk
from contracts.graph import Entity, GraphNeighborhood, Relation
from services.common.logger import get_logger
from services.graph.extractor import EntityRelationshipExtractor

logger = get_logger("graph.store")

DEFAULT_GRAPH_PATH = Path("data/graph/knowledge_graph.json")


class GraphStore:
    """NetworkX-powered local graph store for entity-relation retrieval."""

    def __init__(
        self,
        persistence_path: Path | str | None = None,
        auto_load: bool = True,
        extractor: EntityRelationshipExtractor | None = None,
    ) -> None:
        self.graph = nx.MultiDiGraph()
        self.persistence_path = Path(persistence_path) if persistence_path else DEFAULT_GRAPH_PATH
        self.extractor = extractor or EntityRelationshipExtractor()

        if auto_load and self.persistence_path.exists():
            self.load_from_disk()

    def add_entity(self, entity: Entity) -> None:
        """Adds or updates an entity node in the knowledge graph."""
        norm_name = entity.name.strip()
        if not norm_name:
            return

        if self.graph.has_node(norm_name):
            data = self.graph.nodes[norm_name]
            if entity.category and entity.category != "CONCEPT":
                data["category"] = entity.category

            doc_ids = set(data.get("doc_ids", []))
            if entity.doc_id:
                doc_ids.add(entity.doc_id)
            data["doc_ids"] = list(doc_ids)

            chunk_ids = set(data.get("chunk_ids", []))
            if entity.chunk_id:
                chunk_ids.add(entity.chunk_id)
            data["chunk_ids"] = list(chunk_ids)

            pages = set(data.get("pages", []))
            if entity.page:
                pages.add(entity.page)
            data["pages"] = sorted(pages)

            if entity.bbox:
                bboxes = data.get("bboxes", [])
                if entity.bbox not in bboxes:
                    bboxes.append(entity.bbox)
                data["bboxes"] = bboxes

            if entity.properties:
                data.setdefault("properties", {}).update(entity.properties)
        else:
            self.graph.add_node(
                norm_name,
                name=norm_name,
                category=entity.category,
                doc_ids=[entity.doc_id] if entity.doc_id else [],
                chunk_ids=[entity.chunk_id] if entity.chunk_id else [],
                pages=[entity.page] if entity.page else [],
                bboxes=[entity.bbox] if entity.bbox else [],
                properties=entity.properties or {},
            )

    def add_relation(self, relation: Relation) -> None:
        """Adds a directional predicate edge between two entities."""
        src = relation.source.strip()
        tgt = relation.target.strip()
        if not src or not tgt or src == tgt:
            return

        # Ensure both nodes exist
        if not self.graph.has_node(src):
            self.add_entity(Entity(name=src, doc_id=relation.doc_id, chunk_id=relation.chunk_id))
        if not self.graph.has_node(tgt):
            self.add_entity(Entity(name=tgt, doc_id=relation.doc_id, chunk_id=relation.chunk_id))

        # Check for duplicate edge
        edge_data = {
            "predicate": relation.predicate,
            "weight": relation.weight,
            "evidence_snippet": relation.evidence_snippet or "",
            "doc_id": relation.doc_id,
            "chunk_id": relation.chunk_id,
            "page": relation.page,
            "bbox": relation.bbox,
        }

        # Avoid redundant duplicate edges with same predicate and chunk
        if self.graph.has_edge(src, tgt):
            existing_edges = self.graph.get_edge_data(src, tgt)
            for _, d in existing_edges.items():
                if d.get("predicate") == relation.predicate and d.get("chunk_id") == relation.chunk_id:
                    # Duplicate edge already recorded
                    return

        self.graph.add_edge(src, tgt, **edge_data)

    def index_chunk(self, chunk: Chunk) -> tuple[int, int]:
        """Extracts entities and relations from a single chunk and registers them."""
        res = self.extractor.extract_from_chunk(chunk)
        for e in res.entities:
            self.add_entity(e)
        for r in res.relations:
            self.add_relation(r)
        return len(res.entities), len(res.relations)

    def index_chunks(self, chunks: Sequence[Chunk]) -> tuple[int, int]:
        """Indexes a batch of chunks into the graph."""
        total_e = 0
        total_r = 0
        for c in chunks:
            e_cnt, r_cnt = self.index_chunk(c)
            total_e += e_cnt
            total_r += r_cnt
        logger.info(f"GraphStore: indexed {len(chunks)} chunks -> {total_e} entities, {total_r} relations added")
        return total_e, total_r

    def get_entity(self, name: str) -> Entity | None:
        """Retrieves an entity by exact or normalized name."""
        if not self.graph.has_node(name):
            # Try case-insensitive lookup
            for node in self.graph.nodes:
                if node.lower() == name.lower():
                    name = node
                    break
            else:
                return None

        data = self.graph.nodes[name]
        doc_id = data.get("doc_ids", [None])[0] if data.get("doc_ids") else None
        chunk_id = data.get("chunk_ids", [None])[0] if data.get("chunk_ids") else None
        page = data.get("pages", [None])[0] if data.get("pages") else None
        bbox = data.get("bboxes", [None])[0] if data.get("bboxes") else None

        return Entity(
            name=name,
            category=data.get("category", "CONCEPT"),
            doc_id=doc_id,
            chunk_id=chunk_id,
            page=page,
            bbox=bbox,
            properties=data.get("properties", {}),
        )

    def get_all_entities(self) -> list[Entity]:
        """Returns all entities registered in the graph."""
        entities = []
        for name in self.graph.nodes:
            e = self.get_entity(name)
            if e:
                entities.append(e)
        return entities

    def get_all_relations(self) -> list[Relation]:
        """Returns all directional relation edges in the graph."""
        relations: list[Relation] = []
        for u, v, k, d in self.graph.edges(keys=True, data=True):
            relations.append(
                Relation(
                    source=u,
                    predicate=d.get("predicate", "related_to"),
                    target=v,
                    doc_id=d.get("doc_id"),
                    chunk_id=d.get("chunk_id"),
                    page=d.get("page"),
                    bbox=d.get("bbox"),
                    weight=d.get("weight", 1.0),
                    evidence_snippet=d.get("evidence_snippet"),
                )
            )
        return relations

    def find_entities_in_text(self, text: str) -> list[Entity]:
        """Finds entities from the graph that are mentioned in the query text."""
        extracted = self.extractor.extract_entities(text)
        found: list[Entity] = []
        for e in extracted:
            stored = self.get_entity(e.name)
            if stored:
                found.append(stored)
            else:
                found.append(e)

        # Also search existing graph nodes by direct text match
        text_lower = text.lower()
        for node_name in self.graph.nodes:
            if len(node_name) >= 3 and node_name.lower() in text_lower:
                if not any(f.name.lower() == node_name.lower() for f in found):
                    stored = self.get_entity(node_name)
                    if stored:
                        found.append(stored)

        return found

    def get_neighborhood(self, entity_name: str, max_depth: int = 1) -> GraphNeighborhood:
        """Extracts the k-hop ego-graph neighborhood around a central entity."""
        if not self.graph.has_node(entity_name):
            # Check case-insensitive
            for node in self.graph.nodes:
                if node.lower() == entity_name.lower():
                    entity_name = node
                    break
            else:
                return GraphNeighborhood(
                    center_entities=[entity_name],
                    entities=[],
                    relations=[],
                    connected_chunk_ids=[],
                    depth=max_depth,
                )

        # Ego graph (undirected view for multi-hop expansion)
        undirected = self.graph.to_undirected(as_view=True)
        sub_nodes = nx.single_source_shortest_path_length(undirected, entity_name, cutoff=max_depth).keys()

        discovered_entities: list[Entity] = []
        chunk_ids: set[str] = set()

        for n in sub_nodes:
            e = self.get_entity(n)
            if e:
                discovered_entities.append(e)
            data = self.graph.nodes[n]
            for cid in data.get("chunk_ids", []):
                chunk_ids.add(cid)

        relations: list[Relation] = []
        for u, v, k, d in self.graph.edges(sub_nodes, keys=True, data=True):
            if u in sub_nodes and v in sub_nodes:
                relations.append(
                    Relation(
                        source=u,
                        predicate=d.get("predicate", "related_to"),
                        target=v,
                        doc_id=d.get("doc_id"),
                        chunk_id=d.get("chunk_id"),
                        page=d.get("page"),
                        bbox=d.get("bbox"),
                        weight=d.get("weight", 1.0),
                        evidence_snippet=d.get("evidence_snippet"),
                    )
                )
                if d.get("chunk_id"):
                    chunk_ids.add(d["chunk_id"])

        return GraphNeighborhood(
            center_entities=[entity_name],
            entities=discovered_entities,
            relations=relations,
            connected_chunk_ids=sorted(chunk_ids),
            depth=max_depth,
        )

    def get_connected_chunks(self, entity_names: Sequence[str]) -> list[str]:
        """Returns all chunk IDs that mention or link any of the provided entity names."""
        chunk_ids: set[str] = set()
        for name in entity_names:
            entity = self.get_entity(name)
            if entity and entity.chunk_id:
                chunk_ids.add(entity.chunk_id)

            if self.graph.has_node(name):
                data = self.graph.nodes[name]
                for cid in data.get("chunk_ids", []):
                    chunk_ids.add(cid)
        return sorted(chunk_ids)

    def save_to_disk(self, path: Path | str | None = None) -> None:
        """Persists the graph to disk in structured JSON format."""
        target_path = Path(path) if path else self.persistence_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        nodes_data = []
        for n, d in self.graph.nodes(data=True):
            nodes_data.append({"id": n, **d})

        edges_data = []
        for u, v, k, d in self.graph.edges(keys=True, data=True):
            edges_data.append({"source": u, "target": v, "key": k, **d})

        payload = {
            "version": "1.0",
            "num_nodes": self.graph.number_of_nodes(),
            "num_edges": self.graph.number_of_edges(),
            "nodes": nodes_data,
            "edges": edges_data,
        }

        target_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"GraphStore saved {len(nodes_data)} nodes, {len(edges_data)} edges to {target_path}")

    def load_from_disk(self, path: Path | str | None = None) -> bool:
        """Loads graph state from JSON disk file."""
        target_path = Path(path) if path else self.persistence_path
        if not target_path.exists():
            return False

        try:
            content = json.loads(target_path.read_text(encoding="utf-8"))
            self.graph.clear()

            for n in content.get("nodes", []):
                node_id = n["id"]
                attrs = {k: v for k, v in n.items() if k != "id"}
                self.graph.add_node(node_id, **attrs)

            for e in content.get("edges", []):
                src = e["source"]
                tgt = e["target"]
                attrs = {k: v for k, v in e.items() if k not in ["source", "target", "key"]}
                self.graph.add_edge(src, tgt, **attrs)

            logger.info(
                f"GraphStore loaded {self.graph.number_of_nodes()} nodes, "
                f"{self.graph.number_of_edges()} edges from {target_path}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to load graph from {target_path}: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Returns topological metrics for the knowledge graph."""
        num_nodes = self.graph.number_of_nodes()
        num_edges = self.graph.number_of_edges()
        num_components = (
            nx.number_connected_components(self.graph.to_undirected()) if num_nodes > 0 else 0
        )
        density = nx.density(self.graph) if num_nodes > 1 else 0.0

        categories: dict[str, int] = {}
        for _, d in self.graph.nodes(data=True):
            cat = d.get("category", "CONCEPT")
            categories[cat] = categories.get(cat, 0) + 1

        predicates: dict[str, int] = {}
        for _, _, _, d in self.graph.edges(keys=True, data=True):
            pred = d.get("predicate", "related_to")
            predicates[pred] = predicates.get(pred, 0) + 1

        return {
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "num_connected_components": num_components,
            "density": round(density, 4),
            "entity_categories": categories,
            "predicates": predicates,
        }

    def clear(self) -> None:
        """Clears all nodes and edges from the in-memory graph."""
        self.graph.clear()
