"""Session processor for Knowledge Graph pipeline using Graphiti."""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from utils.rrweb_kg_parser import RRWebKGParser
from kg.graphiti_client import PerceptrGraphitiClient
from kg.episodes import ENTITY_TYPES
from common.services.logger import logger
import uuid


class SessionKGProcessor:
    """Processor for converting rrweb sessions to knowledge graph data using Graphiti."""
    
    def __init__(self, graphiti_client: PerceptrGraphitiClient):
        self.graphiti = graphiti_client
        
    async def process_session_file(self, file_path: str, org_id: int) -> Dict[str, Any]:
        """Main entry point - process entire rrweb session file."""
        try:
            logger.info(f"Starting KG processing for file: {file_path}, org: {org_id}")
            
            # Parse rrweb file and extract KG data
            parser = RRWebKGParser(file_path)
            kg_data = parser.extract_kg_data(org_id)
            
            # Create a comprehensive episode description from the session data
            episode_body = self.create_episode_description(kg_data, org_id)
            
            # Add the episode to Graphiti with custom entity types
            # Graphiti will automatically extract entities and create relationships
            result = await self.graphiti.add_episode(
                name=f"Session {kg_data['session_data']['session_id']}",
                episode_body=episode_body,
                reference_time=self._parse_timestamp(kg_data['session_data']['start_ts']),
                source_description=f"RRWeb session recording from org {org_id}",
                group_id=f"org_{org_id}",
                entity_types=ENTITY_TYPES
            )
            
            logger.info(
                "KG processing completed successfully",
                session_id=kg_data['session_data']['session_id'],
                org_id=org_id,
                episode_result=result.get('success', False)
            )
            
            return {
                'success': result.get('success', False),
                'session_id': kg_data['session_data']['session_id'],
                'file_path': file_path,
                'org_id': org_id,
                'episode_result': result,
                'processing_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(
                "KG processing failed",
                file_path=file_path,
                org_id=org_id,
                error=str(e),
                exc_info=e
            )
            return {
                'success': False,
                'error': str(e),
                'file_path': file_path,
                'org_id': org_id
            }
    
    def create_episode_description(self, kg_data: Dict[str, Any], org_id: int) -> str:
        """Create a natural language description of the session for Graphiti.
        
        Graphiti will automatically extract entities and infer relationships from this description.
        """
        session_data = kg_data['session_data']
        pages = kg_data.get('pages', [])
        actions = kg_data.get('actions', [])
        custom_events = kg_data.get('custom_events', [])
        
        # Build a comprehensive description that describes entities and their relationships
        description_parts = []
        
        # Session info with relationships
        user_id = session_data['user_id']
        device_id = session_data['device_id']
        session_id = session_data['session_id']
        duration = session_data['duration']
        
        description_parts.append(
            f"User {user_id} (org_id: {org_id}) initiated Session {session_id} "
            f"using Device {device_id} ({session_data.get('device_info', {}).get('type', 'unknown')} "
            f"device running {session_data.get('device_info', {}).get('os', 'unknown')} "
            f"with {session_data.get('device_info', {}).get('browser', 'unknown')} browser). "
            f"The session lasted {duration:.2f} seconds and was recorded with recording_id {session_data.get('recording_id', 'unknown')}."
        )
        
        # Page visits with relationships
        if pages:
            description_parts.append(f"During the session, the user had {len(pages)} page views:")
            for i, page in enumerate(pages):
                pv_id = f"{page['path']}_{page['dom_hash']}_{i}_{org_id}"
                description_parts.append(
                    f"PageView {pv_id} was of Page {page['path']} (title: '{page.get('title', 'Unknown')}', "
                    f"template: {page.get('template', 'unknown')}, "
                    f"section: {page.get('section', 'general')}, "
                    f"dom_hash: {page['dom_hash']}). "
                    f"Session {session_id} has this PageView."
                )
        
        # Elements with page relationships
        elements = kg_data.get('elements', [])
        if elements:
            description_parts.append(f"The pages contained {len(elements)} interactive elements:")
            
            cta_elements = [e for e in elements if e.get('category') == 'CTA']
            nav_elements = [e for e in elements if e.get('category') == 'nav']
            form_elements = [e for e in elements if e.get('category') == 'form']
            
            for element in elements[:10]:  # Limit to first 10 elements to avoid too long descriptions
                description_parts.append(
                    f"Element {element['eid']} (label: '{element.get('label', 'unlabeled')}', "
                    f"selector: '{element['selector']}', category: {element.get('category', 'unknown')}) "
                    f"is part of Page {element['page_path']} with dom_hash {element['page_dom_hash']}."
                )
        
        # Actions with element and session relationships
        if actions:
            action_summary = {}
            for action in actions:
                action_type = action['type']
                action_summary[action_type] = action_summary.get(action_type, 0) + 1
            
            action_desc = ", ".join([f"{count} {action_type}" for action_type, count in action_summary.items()])
            description_parts.append(f"Session {session_id} performed {len(actions)} actions: {action_desc}.")
            
            # Describe specific high-value actions
            for action in actions[:5]:  # First 5 actions for detail
                if action.get('element_id'):
                    description_parts.append(
                        f"Action {action['action_id']} (type: {action['type']}) was performed on Element {action['element_id']} "
                        f"by Session {session_id} at {action['ts']}."
                    )
                else:
                    description_parts.append(
                        f"Action {action['action_id']} (type: {action['type']}) was performed "
                        f"by Session {session_id} at {action['ts']}."
                    )
        
        # Custom events with session and action relationships
        if custom_events:
            for event in custom_events:
                description_parts.append(
                    f"CustomEvent {event['cust_id']} (name: '{event['event_name']}') was performed by Session {session_id} "
                    f"at {event['ts']}."
                )
                if event.get('triggered_by_action_id'):
                    description_parts.append(
                        f"This CustomEvent was triggered by Action {event['triggered_by_action_id']}."
                    )
        
        # Network requests with action relationships
        network_requests = kg_data.get('network_requests', [])
        if network_requests:
            description_parts.append(f"Session {session_id} made {len(network_requests)} network requests.")
            for request in network_requests[:3]:  # First 3 requests for detail
                description_parts.append(
                    f"NetworkRequest {request.get('req_id', 'unknown')} to {request.get('url', 'unknown')} "
                    f"was made during Session {session_id}."
                )
                if request.get('triggered_by_action_id'):
                    description_parts.append(
                        f"This NetworkRequest was triggered by Action {request['triggered_by_action_id']}."
                    )
        
        # Performance and errors with session relationships
        performance_metrics = kg_data.get('performance_metrics', [])
        error_events = kg_data.get('error_events', [])
        
        if performance_metrics:
            description_parts.append(f"Session {session_id} recorded {len(performance_metrics)} performance metrics.")
        
        if error_events:
            description_parts.append(f"Session {session_id} encountered {len(error_events)} errors.")
        
        return " ".join(description_parts)
    
    def _parse_timestamp(self, timestamp: Any) -> datetime:
        """Parse timestamp from various formats."""
        if isinstance(timestamp, datetime):
            return timestamp
        elif isinstance(timestamp, (int, float)):
            # Handle both seconds and milliseconds
            if timestamp > 1e10:  # Likely milliseconds
                return datetime.fromtimestamp(timestamp / 1000)
            else:  # Likely seconds
                return datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            try:
                # Try ISO format
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                # Try as timestamp
                return datetime.fromtimestamp(float(timestamp))
        else:
            logger.warning(f"Unknown timestamp format: {timestamp}, using current time")
            return datetime.now()


class BatchKGProcessor:
    """Processor for handling batch KG operations."""
    
    def __init__(self, graphiti_client: PerceptrGraphitiClient):
        self.graphiti = graphiti_client
        self.session_processor = SessionKGProcessor(graphiti_client)
    
    async def process_multiple_sessions(self, session_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process multiple session files in parallel."""
        try:
            results = []
            
            # Process sessions with controlled concurrency
            semaphore = asyncio.Semaphore(5)  # Limit concurrent processing
            
            async def process_single_session(session_info: Dict[str, Any]):
                async with semaphore:
                    return await self.session_processor.process_session_file(
                        session_info['file_path'],
                        session_info['org_id']
                    )
            
            # Create tasks for all sessions
            tasks = [process_single_session(info) for info in session_files]
            
            # Execute all tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            successful = sum(1 for r in results if isinstance(r, dict) and r.get('success', False))
            failed = len(results) - successful
            
            logger.info(
                "Batch KG processing completed",
                total_sessions=len(session_files),
                successful=successful,
                failed=failed
            )
            
            return {
                'success': failed == 0,
                'total_sessions': len(session_files),
                'successful': successful,
                'failed': failed,
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Batch KG processing failed: {str(e)}", exc_info=e)
            return {
                'success': False,
                'error': str(e),
                'total_sessions': len(session_files)
            } 