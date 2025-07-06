"""Utility functions for Knowledge Graph operations."""

from typing import Any, Dict, List
from datetime import datetime


def serialize_graphiti_objects(objects: List[Any]) -> List[Dict[str, Any]]:
    """Convert Graphiti objects to serializable dictionaries.
    
    Args:
        objects: List of objects returned from Graphiti (EntityEdge, etc.)
        
    Returns:
        List of dictionaries suitable for JSON serialization
    """
    serialized_results = []
    
    for obj in objects:
        if hasattr(obj, 'model_dump'):
            # Pydantic model - use model_dump for proper serialization
            serialized_results.append(obj.model_dump())
        elif hasattr(obj, '__dict__'):
            # Regular object - convert attributes to dict
            obj_dict = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # Skip private attributes
                    # Convert datetime objects to ISO strings for JSON serialization
                    if isinstance(value, datetime):
                        obj_dict[key] = value.isoformat()
                    # Handle nested objects recursively
                    elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool)):
                        obj_dict[key] = serialize_graphiti_objects([value])[0] if value else None
                    # Handle lists of objects
                    elif isinstance(value, list):
                        obj_dict[key] = serialize_graphiti_objects(value)
                    else:
                        obj_dict[key] = value
            serialized_results.append(obj_dict)
        elif isinstance(obj, dict):
            # Already a dictionary - ensure datetime conversion
            converted_dict = {}
            for key, value in obj.items():
                if isinstance(value, datetime):
                    converted_dict[key] = value.isoformat()
                else:
                    converted_dict[key] = value
            serialized_results.append(converted_dict)
        else:
            # Fallback - convert to string representation
            serialized_results.append({
                'content': str(obj),
                'type': type(obj).__name__,
                'raw_value': obj if isinstance(obj, (str, int, float, bool)) else str(obj)
            })
    
    return serialized_results


def format_search_results(results: List[Any]) -> List[Dict[str, Any]]:
    """Format search results for API response.
    
    Args:
        results: Raw search results from Graphiti
        
    Returns:
        Formatted results with consistent structure
    """
    formatted = serialize_graphiti_objects(results)
    
    # Add consistent metadata to each result
    for i, result in enumerate(formatted):
        if 'rank' not in result:
            result['rank'] = i + 1
        
        # Ensure we have a display field for UI purposes
        if 'display_text' not in result:
            if 'content' in result:
                result['display_text'] = result['content']
            elif 'name' in result:
                result['display_text'] = result['name']
            elif 'uuid' in result:
                result['display_text'] = f"Entity {result['uuid'][:8]}..."
            else:
                result['display_text'] = f"Result {i + 1}"
    
    return formatted 