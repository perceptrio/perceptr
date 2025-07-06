"""Graphiti client for knowledge graph operations."""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
from graphiti_core import Graphiti
from neo4j import GraphDatabase
from common.services.logger import logger
from settings import settings
from kg.utils import serialize_graphiti_objects

import os

os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY


class PerceptrGraphitiClient:
    """Wrapper around Graphiti for Perceptr-specific KG operations."""
    
    def __init__(self):
        # Initialize Graphiti client with default settings
        self.graphiti_client = None
        self.neo4j_driver = None
        self._setup_client()
    
    def _setup_client(self):
        """Setup the Graphiti client with error handling."""
        try:
            self.graphiti_client = Graphiti(
                uri=settings.NEO4J_URI,
                user=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
            )
            logger.info("Graphiti client initialized successfully")

            self.neo4j_driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            logger.info("Neo4j driver initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Graphiti client: {str(e)}")
            raise
    
    def get_graphiti_client(self) -> Graphiti:
        """Get the underlying Graphiti client."""
        if self.graphiti_client is None:
            self._setup_client()
        return self.graphiti_client
    
    async def add_episode(
        self,
        name: str,
        episode_body: str,
        reference_time: datetime,
        source_description: str = "",
        group_id: str = "",
        entity_types: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add an episode to Graphiti with error handling."""
        try:
            logger.info(f"Adding episode: {name}")
            
            # Note: These warnings are expected for empty databases
            # They will disappear once episodes are added and embeddings are generated
            result = await self.graphiti_client.add_episode(
                name=name,
                episode_body=episode_body,
                reference_time=reference_time,
                source_description=source_description,
                group_id=group_id,
                entity_types=entity_types or {}
            )
            
            logger.info(f"Episode '{name}' added successfully")
            return {'success': True, 'result': result}
            
        except Exception as e:
            logger.error(f"Failed to add episode '{name}': {str(e)}", exc_info=e)
            return {'success': False, 'error': str(e)}
    
    def execute_cypher(self, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query."""
        try:
            with self.neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
        except Exception as e:
            logger.error(f"Cypher query failed: {str(e)}", exc_info=e)
            raise
    
    async def search(
        self, 
        query: str, 
        group_ids: List[str],
        limit: int = 10,
        center_node_uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Perform hybrid search using Graphiti."""
        try:
            logger.info(f"Performing search: {query} for groups: {group_ids}")
            
            result = await self.graphiti_client.search(
                query=query,
                group_ids=group_ids,
                limit=limit,
                center_node_uuid=center_node_uuid
            )
            
            # Convert results to serializable format
            serialized_results = serialize_graphiti_objects(result)
            
            return {'success': True, 'results': serialized_results}
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}", exc_info=e)
            return {'success': False, 'error': str(e)}
    
    async def search_hybrid(self, query: str, top_k: int = 10) -> Dict[str, Any]:
        """Perform hybrid search using Graphiti with simplified parameters."""
        try:
            logger.info(f"Performing hybrid search: {query}")
            
            # Use the built-in search method of Graphiti client
            result = await self.graphiti_client.search(
                query=query,
                # group_ids=[],  # Empty group_ids for global search
                # limit=top_k
            )
            
            # Convert results to serializable format
            serialized_results = serialize_graphiti_objects(result)
            
            return {'success': True, 'results': serialized_results}
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {str(e)}", exc_info=e)
            return {'success': False, 'error': str(e)}
    
    async def build_episodic_memory(
        self,
        group_ids: List[str],
        last_n: Optional[int] = None
    ) -> Dict[str, Any]:
        """Build episodic memory for given groups."""
        try:
            logger.info(f"Building episodic memory for groups: {group_ids}")
            
            await self.graphiti_client.build_episodic_memory(
                group_ids=group_ids,
                last_n=last_n
            )
            
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Failed to build episodic memory: {str(e)}", exc_info=e)
            return {'success': False, 'error': str(e)}
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            stats_query = """
            CALL db.labels() YIELD label
            CALL apoc.cypher.run('MATCH (n:' + label + ') RETURN count(n) as count', {}) YIELD value
            RETURN label, value.count as count
            ORDER BY count DESC
            """
            
            with self.neo4j_driver.session(database=settings.NEO4J_DATABASE) as session:
                result = session.run(stats_query)
                node_counts = {record['label']: record['count'] for record in result}
                
                # Get relationship counts
                rel_query = """
                CALL db.relationshipTypes() YIELD relationshipType
                CALL apoc.cypher.run('MATCH ()-[r:' + relationshipType + ']->() RETURN count(r) as count', {}) YIELD value
                RETURN relationshipType, value.count as count
                ORDER BY count DESC
                """
                
                result = session.run(rel_query)
                relationship_counts = {record['relationshipType']: record['count'] for record in result}
                
                return {
                    'success': True,
                    'node_counts': node_counts,
                    'relationship_counts': relationship_counts,
                    'total_nodes': sum(node_counts.values()),
                    'total_relationships': sum(relationship_counts.values())
                }
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {str(e)}", exc_info=e)
            return {'success': False, 'error': str(e)}
    
    def close(self):
        """Close connections."""
        try:
            if self.neo4j_driver:
                self.neo4j_driver.close()
                logger.info("Neo4j driver closed")
            if self.graphiti_client:
                # Create a new event loop to handle the async close if needed
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, create a task instead
                        asyncio.create_task(self.graphiti_client.close())
                    else:
                        loop.run_until_complete(self.graphiti_client.close())
                except RuntimeError:
                    # No event loop running, create a new one
                    asyncio.run(self.graphiti_client.close())
                logger.info("Graphiti client closed")
        except Exception as e:
            logger.error(f"Error closing connections: {str(e)}")
    
    def __del__(self):
        """Cleanup on deletion."""
        self.close() 