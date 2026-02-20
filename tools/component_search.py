"""
Component Search Tool - ChromaDB RAG for component datasheet search.

Searches cached component datasheets using semantic similarity.
Falls back to DigiKey/Mouser API scraping if no local match found.
"""

import logging
from typing import Optional, List
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings
from schemas.component import Component, ComponentSearchResult

logger = logging.getLogger(__name__)


class ComponentSearchTool:
    """
    Semantic component search using ChromaDB.

    Usage:
        tool = ComponentSearchTool()
        results = tool.search("3.3V LDO regulator 1A low noise")
    """

    def __init__(self):
        self._client: Optional[chromadb.Client] = None
        self._collection = None
        self._initialize()

    def _initialize(self):
        """Initialize ChromaDB client and collection."""
        try:
            # Create persist directory if needed
            persist_dir = Path(settings.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)

            # Initialize ChromaDB client
            self._client = chromadb.PersistentClient(
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )

            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name=settings.chroma_collection_name,
                metadata={"hnsw:space": "cosine"},
            )

            logger.info(f"ChromaDB initialized: {len(self._collection.get()['ids'])} components cached")

        except Exception as e:
            logger.warning(f"ChromaDB initialization failed: {e}")
            self._client = None
            self._collection = None

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        n_results: int = 5,
        min_similarity: float = 0.6,
    ) -> List[ComponentSearchResult]:
        """
        Search for components by semantic similarity.

        Args:
            query: Natural language description of required component
            category: Optional category filter (e.g., "MCU", "Power", "Sensor")
            n_results: Maximum number of results to return
            min_similarity: Minimum similarity threshold (0-1)

        Returns:
            List of ComponentSearchResult with component details and similarity scores
        """
        if not self._collection:
            logger.warning("ChromaDB not available, returning empty results")
            return []

        try:
            # Query ChromaDB
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"category": category} if category else None,
            )

            # Parse results
            search_results = []
            if results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    similarity = 1 - results["distances"][0][i]  # Convert cosine distance to similarity

                    if similarity < min_similarity:
                        continue

                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}

                    component = Component(
                        part_number=metadata.get("part_number", ""),
                        manufacturer=metadata.get("manufacturer", ""),
                        description=metadata.get("description", ""),
                        category=metadata.get("category", "Unknown"),
                        key_specs=metadata.get("key_specs", {}),
                        datasheet_url=metadata.get("datasheet_url", ""),
                        lifecycle_status=metadata.get("lifecycle_status", "unknown"),
                        estimated_cost_usd=metadata.get("estimated_cost_usd"),
                    )

                    search_results.append(
                        ComponentSearchResult(
                            component=component,
                            similarity_score=round(similarity, 3),
                            match_reason=results["documents"][0][i] if results["documents"] else "",
                        )
                    )

            logger.info(f"Component search '{query}': {len(search_results)} results")
            return search_results

        except Exception as e:
            logger.error(f"Component search failed: {e}")
            return []

    def add_component(
        self,
        component: Component,
        description_text: str,
    ) -> bool:
        """
        Add a component to the ChromaDB cache.

        Args:
            component: Component object with all details
            description_text: Full text description for semantic search (e.g., datasheet excerpt)

        Returns:
            True if successfully added
        """
        if not self._collection:
            return False

        try:
            # Check if already exists
            existing = self._collection.get(ids=[component.part_number])
            if existing["ids"]:
                # Update existing
                self._collection.update(
                    ids=[component.part_number],
                    documents=[description_text],
                    metadatas=[{
                        "part_number": component.part_number,
                        "manufacturer": component.manufacturer,
                        "description": component.description,
                        "category": component.category,
                        "key_specs": component.key_specs,
                        "datasheet_url": component.datasheet_url,
                        "lifecycle_status": component.lifecycle_status,
                        "estimated_cost_usd": component.estimated_cost_usd,
                    }],
                )
                logger.debug(f"Updated component: {component.part_number}")
            else:
                # Add new
                self._collection.add(
                    ids=[component.part_number],
                    documents=[description_text],
                    metadatas=[{
                        "part_number": component.part_number,
                        "manufacturer": component.manufacturer,
                        "description": component.description,
                        "category": component.category,
                        "key_specs": component.key_specs,
                        "datasheet_url": component.datasheet_url,
                        "lifecycle_status": component.lifecycle_status,
                        "estimated_cost_usd": component.estimated_cost_usd,
                    }],
                )
                logger.debug(f"Added component: {component.part_number}")

            return True

        except Exception as e:
            logger.error(f"Failed to add component {component.part_number}: {e}")
            return False

    def get_by_part_number(self, part_number: str) -> Optional[Component]:
        """Get a component by its part number from cache."""
        if not self._collection:
            return None

        try:
            results = self._collection.get(ids=[part_number], include=["metadatas"])
            if results["metadatas"] and results["metadatas"][0]:
                metadata = results["metadatas"][0]
                return Component(
                    part_number=metadata.get("part_number", part_number),
                    manufacturer=metadata.get("manufacturer", ""),
                    description=metadata.get("description", ""),
                    category=metadata.get("category", "Unknown"),
                    key_specs=metadata.get("key_specs", {}),
                    datasheet_url=metadata.get("datasheet_url", ""),
                    lifecycle_status=metadata.get("lifecycle_status", "unknown"),
                    estimated_cost_usd=metadata.get("estimated_cost_usd"),
                )
        except Exception as e:
            logger.error(f"Failed to get component {part_number}: {e}")

        return None

    def get_stats(self) -> dict:
        """Get statistics about the component cache."""
        if not self._collection:
            return {"total_components": 0, "categories": {}}

        try:
            all_data = self._collection.get(include=["metadatas"])
            total = len(all_data["ids"])

            categories = {}
            for metadata in all_data["metadatas"] or []:
                cat = metadata.get("category", "Unknown")
                categories[cat] = categories.get(cat, 0) + 1

            return {
                "total_components": total,
                "categories": categories,
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"total_components": 0, "categories": {}}
