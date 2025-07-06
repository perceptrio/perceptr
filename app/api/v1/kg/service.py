"""Knowledge Graph service layer."""

from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session, sessionmaker
from datetime import datetime, timedelta

from api.v1.recording.service import get_recording, check_recording_belonging_to_org
from common.services.logger import logger
from common.services.files_downloader import FilesDownloader
from common.services.s3 import s3_service
from kg.graphiti_client import PerceptrGraphitiClient
from kg.session_processor import SessionKGProcessor, BatchKGProcessor
from utils.rrweb import merge_rrweb_batches
from graphiti_core.utils.maintenance.graph_data_operations import clear_data
from kg.utils import format_search_results


# Global client instance
_graphiti_client = None


def get_graphiti_client() -> PerceptrGraphitiClient:
    """Get or create Graphiti client."""
    global _graphiti_client
    if _graphiti_client is None:
        _graphiti_client = PerceptrGraphitiClient()
    return _graphiti_client


async def setup_kg_database(org_id: int) -> Dict[str, Any]:
    """Set up Knowledge Graph database with constraints and indexes."""
    try:
        logger.info(f"Setting up KG database for org {org_id}")
        
        graphiti_client = get_graphiti_client().get_graphiti_client()
        
        # Use Graphiti's built-in method to initialize database indices and constraints
        # This is the official way according to Graphiti documentation
        
        # Note: This will clear the database and rebuild indices
        logger.info("Clearing existing data and rebuilding database schema...")
        await clear_data(graphiti_client.driver)
        await graphiti_client.build_indices_and_constraints()
        
        # Note about expected warnings:
        # After setup, you may see warnings about missing properties like:
        # - "name_embedding" - created when entities are added with embeddings
        # - "fact_embedding" - created when facts/relationships are processed  
        # - "episodes" - created when episodes are added to track provenance
        # These warnings are expected for empty databases and will disappear once data is added.
        
        logger.info(f"KG database setup completed for org {org_id}")
        logger.info("Note: Initial queries may show warnings about missing embedding properties - this is expected for empty databases")
        
        return {
            "success": True,
            "message": "Knowledge Graph database indices and constraints created successfully",
            "org_id": org_id,
            "note": "Initial queries may show warnings about missing embedding properties (name_embedding, fact_embedding, episodes) - this is expected for empty databases and will resolve once episodes are added."
        }
        
    except Exception as e:
        logger.error(f"KG database setup failed for org {org_id}: {str(e)}", exc_info=e)
        return {'success': False, 'error': str(e)}


async def get_kg_stats(org_id: int) -> Dict[str, Any]:
    """Get Knowledge Graph statistics for the organization."""
    try:
        client = get_graphiti_client()
        
        # Get overall database stats
        db_stats = client.get_database_stats()
        
        # Get org-specific stats
        org_stats_query = """
        MATCH (n {org_id: $org_id})
        RETURN labels(n) as labels, count(n) as count
        """
        org_results = client.execute_cypher(org_stats_query, {"org_id": org_id})
        
        org_node_counts = {}
        for result in org_results:
            # Get the primary label (excluding 'Entity' if present)
            labels = result['labels']
            primary_label = next((label for label in labels if label != 'Entity'), labels[0] if labels else 'Unknown')
            org_node_counts[primary_label] = result['count']
        
        total_org_nodes = sum(org_node_counts.values())
        
        # Check if database is empty - this helps explain why warnings might appear
        is_empty_for_org = total_org_nodes == 0
        warning_explanation = ""
        if is_empty_for_org:
            warning_explanation = (
                "Note: Since no data has been added yet, you may see warnings about missing properties "
                "(name_embedding, fact_embedding, episodes) during searches. These warnings are expected "
                "for empty databases and will disappear once episodes are added."
            )
        
        return {
            'success': True,
            'org_stats': {
                'node_counts': org_node_counts,
                'total_nodes': total_org_nodes,
                'is_empty': is_empty_for_org
            },
            'database_stats': db_stats,
            'warning_explanation': warning_explanation
        }
        
    except Exception as e:
        logger.error(f"Failed to get KG stats for org {org_id}: {str(e)}", exc_info=e)
        return {'success': False, 'error': str(e)}


async def process_recording_background(
    recording_id: int,
    org_id: int,
    processing_id: str,
    db: Session,
):
    """Background task to process a single recording."""
    try:
        logger.info(
            f"Processing recording {recording_id} for KG extraction",
            org_id=org_id,
            processing_id=processing_id
        )
        
        # Validate recording exists and belongs to org
        recording = check_recording_belonging_to_org(db, recording_id, org_id)
        
        if not recording.session_id:
            raise ValueError(f"Recording {recording_id} has no session_id")
        
        session_id = recording.session_id
        
        client = get_graphiti_client()
        processor = SessionKGProcessor(client)
        
        # Download and consolidate session batches following per service logic
        logger.info(
            f"Downloading session batches for session {session_id}",
            org_id=org_id,
            processing_id=processing_id
        )
        
        with FilesDownloader(
            s3_service.get_s3_client(), keep_temp_dir=False
        ) as downloader:
            session_prefix = f"{org_id}/{session_id}/"
            local_file_paths = downloader.download_all_session_batches(session_prefix)
            
            logger.info(
                "Session files downloaded",
                session_id=session_id,
                org_id=org_id,
                processing_id=processing_id,
                file_count=len(local_file_paths),
            )
            
            if not local_file_paths:
                logger.warning(
                    f"No session batch files found for session {session_id}",
                    org_id=org_id,
                    processing_id=processing_id
                )
                raise ValueError(f"No session batch files found for session {session_id}")
            
            # Merge the rrweb batches into a single consolidated file
            merged_file_path = merge_rrweb_batches(local_file_paths)
            logger.info(
                "Session files merged successfully",
                session_id=session_id,
                org_id=org_id,
                processing_id=processing_id,
                output_path=merged_file_path,
            )
            
            # Process the consolidated file for KG extraction
            result = await processor.process_session_file(merged_file_path, org_id)
            
            if result['success']:
                logger.info(
                    f"Successfully processed recording {recording_id} for KG",
                    org_id=org_id,
                    processing_id=processing_id,
                    session_id=session_id
                )
            else:
                logger.error(
                    f"Failed to process recording {recording_id} for KG",
                    org_id=org_id,
                    processing_id=processing_id,
                    session_id=session_id,
                    error=result.get('error')
                )
    
    except Exception as e:
        logger.error(
            f"Background processing failed for recording {recording_id}",
            org_id=org_id,
            processing_id=processing_id,
            error=str(e),
            exc_info=e
        )


async def process_batch_background(
    recording_ids: List[int],
    org_id: int,
    processing_id: str,
    db: Session,
):
    """Background task to process multiple recordings."""
    try:
        logger.info(
            f"Processing batch of {len(recording_ids)} recordings for KG extraction",
            org_id=org_id,
            processing_id=processing_id
        )
        
        # Validate all recordings exist and belong to org
        recordings = []
        for recording_id in recording_ids:
            recording = check_recording_belonging_to_org(db, recording_id, org_id)
            if not recording.session_id:
                logger.warning(
                    f"Recording {recording_id} has no session_id, skipping",
                    org_id=org_id,
                    processing_id=processing_id
                )
                continue
            recordings.append(recording)
        
        client = get_graphiti_client()
        batch_processor = BatchKGProcessor(client)
        
        # Prepare session file info list by downloading and consolidating batches
        session_files = []
        for recording in recordings:
            try:
                session_id = recording.session_id
                logger.info(
                    f"Downloading session batches for recording {recording.id}, session {session_id}",
                    org_id=org_id,
                    processing_id=processing_id
                )
                
                with FilesDownloader(
                    s3_service.get_s3_client(), keep_temp_dir=False
                ) as downloader:
                    session_prefix = f"{org_id}/{session_id}/"
                    local_file_paths = downloader.download_all_session_batches(session_prefix)
                    
                    if not local_file_paths:
                        logger.warning(
                            f"No session batch files found for recording {recording.id}, session {session_id}",
                            org_id=org_id,
                            processing_id=processing_id
                        )
                        continue
                    
                    # Merge the rrweb batches into a single consolidated file
                    merged_file_path = merge_rrweb_batches(local_file_paths)
                    logger.info(
                        f"Session files merged for recording {recording.id}",
                        session_id=session_id,
                        org_id=org_id,
                        processing_id=processing_id,
                        output_path=merged_file_path,
                    )
                    
                    session_files.append({
                        'file_path': merged_file_path,
                        'org_id': org_id,
                        'recording_id': recording.id,
                        'session_id': session_id
                    })
                    
            except Exception as e:
                logger.error(
                    f"Failed to prepare session file for recording {recording.id}",
                    org_id=org_id,
                    processing_id=processing_id,
                    error=str(e),
                    exc_info=e
                )
                continue
        
        if not session_files:
            logger.warning(
                f"No valid session files prepared for batch processing",
                org_id=org_id,
                processing_id=processing_id
            )
            return
        
        # Process all sessions in batch
        result = await batch_processor.process_multiple_sessions(session_files)
        
        logger.info(
            f"Batch processing completed",
            org_id=org_id,
            processing_id=processing_id,
            total_sessions=result.get('total_sessions', 0),
            successful=result.get('successful', 0),
            failed=result.get('failed', 0)
        )
    
    except Exception as e:
        logger.error(
            f"Batch background processing failed",
            org_id=org_id,
            processing_id=processing_id,
            error=str(e),
            exc_info=e
        )


# Query services
async def execute_cypher_query(query: str, parameters: Dict[str, Any], org_id: int) -> Dict[str, Any]:
    """Execute Cypher queries with org isolation."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        # Add org_id filter to query for security
        safe_query = add_org_filter(query, org_id)
        
        # Execute the query
        result = client.execute_cypher(safe_query, parameters)
        
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(
            "Cypher query executed",
            org_id=org_id,
            query_length=len(query),
            result_count=len(result),
            query_time_ms=query_time
        )
        
        return {
            'success': True,
            'data': result,
            'query_time_ms': query_time
        }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Cypher query failed",
            org_id=org_id,
            query=query,
            error=str(e),
            query_time_ms=query_time,
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


async def perform_hybrid_search(question: str, top_k: int, org_id: int) -> Dict[str, Any]:
    """Perform hybrid search using Graphiti."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        # Add org context to the search query
        org_context_query = f"org_id:{org_id} {question}"
        
        # Perform hybrid search
        search_result = await client.search_hybrid(org_context_query, top_k)
        
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if search_result["success"]:
            # Convert Graphiti objects to dictionaries for API response
            results_data = format_search_results(search_result["results"])
            
            logger.info(
                "Hybrid search completed",
                org_id=org_id,
                question=question,
                result_count=len(results_data),
                query_time_ms=query_time
            )
            
            return {
                'success': True,
                'data': results_data,
                'query_time_ms': query_time
            }
        else:
            return {
                'success': False,
                'error': search_result["error"],
                'query_time_ms': query_time
            }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Hybrid search failed",
            org_id=org_id,
            question=question,
            error=str(e),
            query_time_ms=query_time,
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


# Analytics services
async def get_session_journey(session_id: str, org_id: int) -> Dict[str, Any]:
    """Get complete user journey for a session."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        query = """
        MATCH (s:Session {session_id: $session_id, org_id: $org_id})
        OPTIONAL MATCH (s)-[:HAS_PAGEVIEW]->(pv:PageView)-[:OF_PAGE]->(p:Page)
        OPTIONAL MATCH (s)-[:PERFORMED]->(a:Action)
        OPTIONAL MATCH (a)-[:ON]->(e:Element)
        OPTIONAL MATCH (s)-[:PERFORMED]->(ce:CustomEvent)
        
        RETURN s, 
               collect(DISTINCT {pageview: pv, page: p}) as pages,
               collect(DISTINCT {action: a, element: e}) as actions,
               collect(DISTINCT ce) as custom_events
        ORDER BY pv.timestamp, a.ts
        """
        
        parameters = {
            "session_id": session_id,
            "org_id": org_id
        }
        
        result = client.execute_cypher(query, parameters)
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        if result:
            # Process and structure the journey data
            journey_data = result[0]
            processed_data = {
                "session": journey_data.get("s", {}),
                "pages": journey_data.get("pages", []),
                "actions": journey_data.get("actions", []),
                "custom_events": journey_data.get("custom_events", [])
            }
            
            return {
                'success': True,
                'data': [processed_data],
                'query_time_ms': query_time,
                'total_count': 1
            }
        else:
            return {
                'success': False,
                'error': "Session not found",
                'query_time_ms': query_time
            }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Session journey query failed",
            session_id=session_id,
            org_id=org_id,
            error=str(e),
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


async def get_abandoned_carts(org_id: int, hours_back: int) -> Dict[str, Any]:
    """Find sessions that added to cart but never completed checkout."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        # Calculate timestamp for filtering
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        
        query = """
        MATCH (s:Session {org_id: $org_id})
        WHERE s.start_ts > $cutoff_timestamp
        
        // Find sessions with add-to-cart actions
        MATCH (s)-[:PERFORMED]->(a:Action)-[:ON]->(e:Element)
        WHERE e.label =~ '(?i).*add.*cart.*' OR e.category = 'CTA'
        
        // Ensure they don't have checkout completion
        WHERE NOT EXISTS {
            MATCH (s)-[:PERFORMED]->(ce:CustomEvent)
            WHERE ce.event_name IN ['checkout_completed', 'purchase_completed', 'order_completed']
        }
        
        RETURN s.session_id as session_id,
               s.user_id as user_id,
               s.start_ts as start_time,
               count(a) as cart_actions,
               collect(DISTINCT e.label) as elements_clicked
        ORDER BY s.start_ts DESC
        LIMIT 100
        """
        
        parameters = {
            "org_id": org_id,
            "cutoff_timestamp": cutoff_timestamp
        }
        
        result = client.execute_cypher(query, parameters)
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(
            "Abandoned carts query completed",
            org_id=org_id,
            hours_back=hours_back,
            result_count=len(result),
            query_time_ms=query_time
        )
        
        return {
            'success': True,
            'data': result,
            'query_time_ms': query_time,
            'total_count': len(result)
        }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Abandoned carts query failed",
            org_id=org_id,
            hours_back=hours_back,
            error=str(e),
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


async def analyze_conversion_funnel(org_id: int, steps: str, days_back: int) -> Dict[str, Any]:
    """Analyze conversion funnel with abandonment points."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        # Parse funnel steps
        funnel_steps = [step.strip() for step in steps.split(',')]
        
        if len(funnel_steps) < 2:
            return {
                'success': False,
                'error': "At least 2 funnel steps required"
            }
        
        # Calculate timestamp for filtering
        cutoff_time = datetime.now() - timedelta(days=days_back)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        
        funnel_results = []
        
        for i, step in enumerate(funnel_steps):
            if i == 0:
                # First step - count all users who performed this action
                query = """
                MATCH (s:Session {org_id: $org_id})
                WHERE s.start_ts > $cutoff_timestamp
                
                MATCH (s)-[:PERFORMED]->(a:Action)-[:ON]->(e:Element)
                WHERE e.label =~ $step_pattern OR e.category =~ $step_pattern
                
                RETURN count(DISTINCT s.session_id) as user_count
                """
                
                parameters = {
                    "org_id": org_id,
                    "cutoff_timestamp": cutoff_timestamp,
                    "step_pattern": f"(?i).*{step}.*"
                }
                
                result = client.execute_cypher(query, parameters)
                entered_count = result[0]["user_count"] if result else 0
                
                funnel_results.append({
                    "step_name": step,
                    "users_entered": entered_count,
                    "users_completed": entered_count,
                    "conversion_rate": 100.0,
                    "drop_off_rate": 0.0
                })
                
            else:
                # Subsequent steps - count users who completed previous step AND this step
                prev_steps = funnel_steps[:i+1]
                
                query = """
                MATCH (s:Session {org_id: $org_id})
                WHERE s.start_ts > $cutoff_timestamp
                
                // Must have completed all previous steps
                """
                
                for j, prev_step in enumerate(prev_steps):
                    query += f"""
                MATCH (s)-[:PERFORMED]->(a{j}:Action)-[:ON]->(e{j}:Element)
                WHERE e{j}.label =~ $step_pattern_{j} OR e{j}.category =~ $step_pattern_{j}
                """
                
                query += "\nRETURN count(DISTINCT s.session_id) as user_count"
                
                parameters = {"org_id": org_id, "cutoff_timestamp": cutoff_timestamp}
                for j, prev_step in enumerate(prev_steps):
                    parameters[f"step_pattern_{j}"] = f"(?i).*{prev_step}.*"
                
                result = client.execute_cypher(query, parameters)
                completed_count = result[0]["user_count"] if result else 0
                
                # Calculate rates
                prev_count = funnel_results[i-1]["users_completed"]
                conversion_rate = (completed_count / prev_count * 100) if prev_count > 0 else 0
                drop_off_rate = 100 - conversion_rate
                
                funnel_results.append({
                    "step_name": step,
                    "users_entered": prev_count,
                    "users_completed": completed_count,
                    "conversion_rate": round(conversion_rate, 2),
                    "drop_off_rate": round(drop_off_rate, 2)
                })
        
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(
            "Conversion funnel analysis completed",
            org_id=org_id,
            steps=funnel_steps,
            days_back=days_back,
            query_time_ms=query_time
        )
        
        return {
            'success': True,
            'data': funnel_results,
            'query_time_ms': query_time,
            'total_count': len(funnel_results)
        }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Conversion funnel analysis failed",
            org_id=org_id,
            steps=steps,
            days_back=days_back,
            error=str(e),
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


async def get_popular_elements(org_id: int, hours_back: int, limit: int) -> Dict[str, Any]:
    """Get most clicked elements in the given time period."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        # Calculate timestamp for filtering
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        
        query = """
        MATCH (s:Session {org_id: $org_id})
        WHERE s.start_ts > $cutoff_timestamp
        
        MATCH (s)-[:PERFORMED]->(a:Action {type: 'click'})-[:ON]->(e:Element)
        
        RETURN e.label as element_label,
               e.selector as element_selector,
               e.category as element_category,
               e.page_path as page_path,
               count(a) as click_count,
               count(DISTINCT s.session_id) as unique_sessions
        ORDER BY click_count DESC
        LIMIT $limit
        """
        
        parameters = {
            "org_id": org_id,
            "cutoff_timestamp": cutoff_timestamp,
            "limit": limit
        }
        
        result = client.execute_cypher(query, parameters)
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(
            "Popular elements query completed",
            org_id=org_id,
            hours_back=hours_back,
            result_count=len(result),
            query_time_ms=query_time
        )
        
        return {
            'success': True,
            'data': result,
            'query_time_ms': query_time,
            'total_count': len(result)
        }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Popular elements query failed",
            org_id=org_id,
            hours_back=hours_back,
            error=str(e),
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


async def detect_rage_clicks(org_id: int, hours_back: int, min_clicks: int, time_window_seconds: int) -> Dict[str, Any]:
    """Detect potential rage clicking patterns."""
    start_time = datetime.now()
    
    try:
        client = get_graphiti_client()
        
        # Calculate timestamp for filtering
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        
        query = """
        MATCH (s:Session {org_id: $org_id})
        WHERE s.start_ts > $cutoff_timestamp
        
        MATCH (s)-[:PERFORMED]->(a:Action {type: 'click'})-[:ON]->(e:Element)
        
        // Group actions by session and element
        WITH s, e, collect(a) as actions
        WHERE size(actions) >= $min_clicks
        
        // Check if clicks happened within time window
        WITH s, e, actions,
             [action in actions | action.ts] as timestamps
        
        // Calculate time differences and find rapid clicking
        WITH s, e, actions, timestamps,
             [i in range(0, size(timestamps)-2) | 
              timestamps[i+1] - timestamps[i]] as time_diffs
        
        WHERE any(diff in time_diffs WHERE diff <= $time_window_ms)
        
        RETURN s.session_id as session_id,
               s.user_id as user_id,
               e.label as element_label,
               e.selector as element_selector,
               e.page_path as page_path,
               size(actions) as click_count,
               min(time_diffs) as min_time_between_clicks
        ORDER BY click_count DESC, min_time_between_clicks ASC
        """
        
        parameters = {
            "org_id": org_id,
            "cutoff_timestamp": cutoff_timestamp,
            "min_clicks": min_clicks,
            "time_window_ms": time_window_seconds * 1000
        }
        
        result = client.execute_cypher(query, parameters)
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        
        logger.info(
            "Rage clicks detection completed",
            org_id=org_id,
            hours_back=hours_back,
            result_count=len(result),
            query_time_ms=query_time
        )
        
        return {
            'success': True,
            'data': result,
            'query_time_ms': query_time,
            'total_count': len(result)
        }
        
    except Exception as e:
        query_time = (datetime.now() - start_time).total_seconds() * 1000
        logger.error(
            "Rage clicks detection failed",
            org_id=org_id,
            hours_back=hours_back,
            error=str(e),
            exc_info=e
        )
        
        return {
            'success': False,
            'error': str(e),
            'query_time_ms': query_time
        }


def add_org_filter(cypher_query: str, org_id: int) -> str:
    """Add org_id filter to Cypher query for security."""
    # This is a simplified implementation
    # In production, you'd want more sophisticated query parsing
    
    query_lower = cypher_query.lower().strip()
    
    # If query already has WHERE clause, add AND condition
    if " where " in query_lower:
        # Find the WHERE clause and add org_id filter
        parts = cypher_query.split(" WHERE ", 1)
        if len(parts) == 2:
            modified_query = f"{parts[0]} WHERE ({parts[1]}) AND n.org_id = {org_id}"
        else:
            parts = cypher_query.split(" where ", 1)
            modified_query = f"{parts[0]} WHERE ({parts[1]}) AND n.org_id = {org_id}"
    else:
        # Add WHERE clause with org_id filter
        # This is a very basic implementation - in production you'd need proper parsing
        if " return " in query_lower:
            parts = cypher_query.split(" RETURN ", 1)
            if len(parts) == 2:
                modified_query = f"{parts[0]} WHERE n.org_id = {org_id} RETURN {parts[1]}"
            else:
                parts = cypher_query.split(" return ", 1)
                modified_query = f"{parts[0]} WHERE n.org_id = {org_id} RETURN {parts[1]}"
        else:
            # Fallback - just append the filter
            modified_query = f"{cypher_query} WHERE n.org_id = {org_id}"
    
    logger.debug(
        "Applied org filter to query",
        original_query=cypher_query,
        modified_query=modified_query,
        org_id=org_id
    )
    
    return modified_query 