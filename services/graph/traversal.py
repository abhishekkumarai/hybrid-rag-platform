"""Graph Traversal, Multi-Hop Associative Pathfinding, and Community Detection for Phase 13 GraphRAG."""

from __future__ import annotations

import time
from typing import Sequence

import networkx as nx
from networkx.algorithms import community

from contracts.graph import (
    GraphCommunity,
    GraphRAGResponse,
    Relation,
)
from services.common.logger import get_logger
from services.graph.store import GraphStore

logger = get_logger("graph.traversal")


class GraphTraverser:
    """Performs multi-hop graph traversal, cross-document associative linking, and community detection."""

    def __init__(self, graph_store: GraphStore) -> None:
        self.store = graph_store

    def query_graph(
        self,
        query_text: str,
        max_hops: int = 2,
        max_entities: int = 20,
        min_edge_weight: float = 0.1,
    ) -> GraphRAGResponse:
        """Executes full GraphRAG traversal pipeline for a natural language query."""
        start_time = time.perf_counter()

        # 1. Identify focal entities directly mentioned in query
        matched_entities = self.store.find_entities_in_text(query_text)
        if not matched_entities:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return GraphRAGResponse(
                query=query_text,
                matched_entities=[],
                relations=[],
                subgraph_text="",
                connected_chunk_ids=[],
                communities=[],
                duration_ms=round(elapsed_ms, 2),
            )

        focal_names = [e.name for e in matched_entities]

        # 2. Traverse k-hop neighborhood from focal entities
        discovered_relations: list[Relation] = []
        discovered_chunk_ids: set[str] = set()
        seen_triples: set[tuple[str, str, str]] = set()

        for focal_name in focal_names:
            nb = self.store.get_neighborhood(focal_name, max_depth=max_hops)
            for cid in nb.connected_chunk_ids:
                discovered_chunk_ids.add(cid)

            for rel in nb.relations:
                if rel.weight >= min_edge_weight:
                    key = (rel.source, rel.predicate, rel.target)
                    if key not in seen_triples:
                        seen_triples.add(key)
                        discovered_relations.append(rel)

        # 3. If multiple focal entities, check for associative paths connecting them
        if len(focal_names) >= 2:
            undirected = self.store.graph.to_undirected(as_view=True)
            for i in range(len(focal_names)):
                for j in range(i + 1, len(focal_names)):
                    src = focal_names[i]
                    tgt = focal_names[j]
                    if (
                        self.store.graph.has_node(src)
                        and self.store.graph.has_node(tgt)
                        and nx.has_path(undirected, src, tgt)
                    ):
                        try:
                            path = nx.shortest_path(undirected, src, tgt)
                            # Add edges along the path
                            for step_idx in range(len(path) - 1):
                                u, v = path[step_idx], path[step_idx + 1]
                                edges = self.store.graph.get_edge_data(u, v) or self.store.graph.get_edge_data(v, u) or {}
                                for _, d in edges.items():
                                    key = (u, d.get("predicate", "related_to"), v)
                                    if key not in seen_triples:
                                        seen_triples.add(key)
                                        discovered_relations.append(
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
                                        discovered_chunk_ids.add(d["chunk_id"])
                        except Exception:
                            pass

        # 4. Filter and cap relations
        discovered_relations.sort(key=lambda r: r.weight, reverse=True)
        top_relations = discovered_relations[:max_entities]

        # 5. Format relational markdown
        subgraph_text = self.format_subgraph_markdown(top_relations)

        # 6. Community Detection on active subgraph
        relevant_nodes = set(focal_names)
        for r in top_relations:
            relevant_nodes.add(r.source)
            relevant_nodes.add(r.target)

        communities = self.detect_subgraph_communities(relevant_nodes)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"GraphTraverser: query='{query_text}' -> {len(matched_entities)} focal entities, "
            f"{len(top_relations)} relations, {len(discovered_chunk_ids)} connected chunks in {elapsed_ms:.2f}ms"
        )

        return GraphRAGResponse(
            query=query_text,
            matched_entities=matched_entities,
            relations=top_relations,
            subgraph_text=subgraph_text,
            connected_chunk_ids=sorted(discovered_chunk_ids),
            communities=communities,
            duration_ms=round(elapsed_ms, 2),
        )

    def find_associative_path(self, source_entity: str, target_entity: str) -> list[str]:
        """Finds the shortest relational path connecting two entities across documents."""
        undirected = self.store.graph.to_undirected(as_view=True)
        if (
            self.store.graph.has_node(source_entity)
            and self.store.graph.has_node(target_entity)
            and nx.has_path(undirected, source_entity, target_entity)
        ):
            return nx.shortest_path(undirected, source_entity, target_entity)
        return []

    def detect_subgraph_communities(self, node_subset: set[str]) -> list[GraphCommunity]:
        """Detects modular communities among the specified subset of nodes."""
        if len(node_subset) < 3:
            return []

        undirected = self.store.graph.to_undirected()
        subgraph = undirected.subgraph(node_subset)

        communities_list: list[GraphCommunity] = []
        try:
            # Use greedy modularity community detection
            detected = community.greedy_modularity_communities(subgraph)
            for idx, comm in enumerate(detected):
                members = sorted(list(comm))
                if len(members) >= 2:
                    # Pick the node with highest degree as theme representative
                    degrees = dict(subgraph.degree(members))
                    top_node = max(degrees, key=degrees.get) if degrees else members[0]
                    communities_list.append(
                        GraphCommunity(
                            community_id=idx,
                            name=f"Cluster: {top_node}",
                            entities=members,
                            summary=f"Community centered around {top_node} connecting {', '.join(members[:5])}",
                        )
                    )
        except Exception as e:
            logger.debug(f"Community detection fallback: {e}")

        return communities_list

    def format_subgraph_markdown(self, relations: Sequence[Relation], max_triples: int = 15) -> str:
        """Formats graph relations into clean, dense markdown for prompt augmentation."""
        if not relations:
            return ""

        lines: list[str] = [
            "### Relational Knowledge Graph Context:",
            "The following entity-relationship facts were verified from indexed documents:",
        ]

        for rel in relations[:max_triples]:
            doc_badge = f" [Doc: {rel.doc_id}" if rel.doc_id else ""
            if rel.page and doc_badge:
                doc_badge += f", Page {rel.page}"
            if doc_badge:
                doc_badge += "]"

            # Human-readable predicate formatting
            pred_display = rel.predicate.replace("_", " ")
            lines.append(f"- **{rel.source}** —_{pred_display}_—> **{rel.target}**{doc_badge}")

        return "\n".join(lines)
