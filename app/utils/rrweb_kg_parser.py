"""Enhanced RRWeb parser for Knowledge Graph data extraction."""

import hashlib
import json
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse, parse_qs

from bs4 import BeautifulSoup
from utils.rrweb import RRWebSessionUtils
from common.services.logger import logger


class RRWebKGParser(RRWebSessionUtils):
    """Enhanced RRWeb parser for extracting Knowledge Graph data."""
    
    def __init__(self, file_path: str):
        super().__init__(file_path)
        self.dom_hash_cache: Dict[str, str] = {}
        self.element_cache: Dict[str, Dict[str, Any]] = {}
        self.current_page_hash: Optional[str] = None
        self.current_url: Optional[str] = None
        self.action_counter = 0
        
    def extract_kg_data(self, org_id: int) -> Dict[str, Any]:
        """Extract all KG-relevant data from the session."""
        logger.info(f"Starting KG data extraction for session {self.session_id}")
        
        # Process events in chronological order
        sorted_events = sorted(self.events, key=lambda e: e.get('timestamp', 0))
        
        session_data = self.extract_session_data(org_id)
        pages_data = []
        elements_data = []
        actions_data = []
        custom_events_data = []
        network_requests_data = []
        
        for event in sorted_events:
            event_type = event.get('type')
            
            if event_type == 2:  # FullSnapshot
                page_data, page_elements = self.extract_page_from_event(event, org_id)
                if page_data:
                    pages_data.append(page_data)
                    elements_data.extend(page_elements)
                    
            elif event_type == 3:  # IncrementalSnapshot
                data = event.get('data', {})
                source = data.get('source')
                
                if source == 2:  # MouseInteraction
                    action = self.extract_action_from_event(event, org_id)
                    if action:
                        actions_data.append(action)
                        
                elif source == 3:  # Scroll
                    action = self.extract_scroll_action(event, org_id)
                    if action:
                        actions_data.append(action)
                        
                elif source == 5:  # Input
                    action = self.extract_input_action(event, org_id)
                    if action:
                        actions_data.append(action)
                        
                elif source == 6:  # MediaInteraction
                    action = self.extract_media_action(event, org_id)
                    if action:
                        actions_data.append(action)
                        
            elif event_type == 5:  # Custom
                custom_event = self.extract_custom_event(event, org_id)
                if custom_event:
                    custom_events_data.append(custom_event)
        
        logger.info(
            "KG data extraction completed",
            session_id=self.session_id,
            pages=len(pages_data),
            elements=len(elements_data),
            actions=len(actions_data),
            custom_events=len(custom_events_data)
        )
        
        return {
            'session_data': session_data,
            'pages': pages_data,
            'elements': elements_data,
            'actions': actions_data,
            'custom_events': custom_events_data,
            'network_requests': network_requests_data,
            'performance_metrics': []  # TODO: implement performance metrics extraction
        }
    
    def extract_session_data(self, org_id: int) -> Dict[str, Any]:
        """Extract session-level data."""
        # Parse user agent for device info
        user_agent = self.get_user_agent_from_events()
        device_info = self.parse_user_agent(user_agent) if user_agent else {}
        
        # Generate IDs with defaults
        user_id = self.userIdentity.get('id', 'anonymous') if self.userIdentity else 'anonymous'
        device_id = self.generate_device_id(user_agent, device_info)
        
        return {
            'session_id': str(self.session_id),
            'user_id': str(user_id),
            'device_id': device_id,
            'start_ts': self.get_start_time(),
            'end_ts': self.get_end_time(),
            'duration': self.duration,
            'device_info': device_info,
            'is_authenticated': user_id != 'anonymous',
            'ip': None,  # Not available from rrweb data
            'geo': None,  # Not available from rrweb data
            'recording_id': None,  # Will be set from external context
            'org_id': org_id
        }
    
    def extract_page_from_event(self, event: Dict[str, Any], org_id: int) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Extract page and elements from FullSnapshot event."""
        try:
            data = event.get('data', {})
            node = data.get('node', {})
            
            if not node:
                return None, []
            
            # Calculate DOM hash
            dom_hash = self.calculate_dom_hash(node)
            
            # Extract URL from meta or current context
            url = self.extract_url_from_node(node)
            if not url:
                return None, []
            
            parsed_url = urlparse(url)
            path = parsed_url.path or "/"
            
            # Cache current page context
            self.current_page_hash = dom_hash
            self.current_url = url
            
            # Extract page data
            page_data = {
                'path': path,
                'title': self.extract_title_from_node(node),
                'dom_hash': dom_hash,
                'template': self.classify_page_template(path),
                'section': self.classify_page_section(path),
                'timestamp': datetime.fromtimestamp(event.get('timestamp', 0) / 1000),
                'org_id': org_id
            }
            
            # Extract elements
            elements = self.extract_elements_from_node(node, path, dom_hash, org_id)
            
            return page_data, elements
            
        except Exception as e:
            logger.error(f"Error extracting page from event: {str(e)}")
            return None, []
    
    def calculate_dom_hash(self, node: Dict[str, Any]) -> str:
        """Calculate SHA-1 hash of DOM structure."""
        # Create a simplified representation of the DOM structure
        dom_structure = self.simplify_dom_structure(node)
        dom_string = json.dumps(dom_structure, sort_keys=True)
        
        # Calculate SHA-1 hash
        hash_obj = hashlib.sha1(dom_string.encode('utf-8'))
        return hash_obj.hexdigest()[:16]  # Use first 16 characters
    
    def simplify_dom_structure(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Create a simplified DOM structure for hashing."""
        simplified = {
            'tag': node.get('tagName', '').lower(),
            'type': node.get('type'),
        }
        
        # Include important attributes that affect structure
        attributes = node.get('attributes', {})
        important_attrs = ['id', 'class', 'type', 'role', 'data-testid']
        for attr in important_attrs:
            if attr in attributes:
                simplified[attr] = attributes[attr]
        
        # Recursively process children
        children = node.get('childNodes', [])
        if children:
            simplified['children'] = []
            for child in children:
                if isinstance(child, dict) and child.get('type') == 1:  # Element nodes only
                    simplified['children'].append(self.simplify_dom_structure(child))
        
        return simplified
    
    def extract_elements_from_node(self, node: Dict[str, Any], page_path: str, dom_hash: str, org_id: int) -> List[Dict[str, Any]]:
        """Extract clickable elements from DOM node."""
        elements = []
        self._extract_elements_recursive(node, elements, page_path, dom_hash, org_id)
        return elements
    
    def _extract_elements_recursive(self, node: Dict[str, Any], elements: List[Dict[str, Any]], 
                                  page_path: str, dom_hash: str, org_id: int, path: str = "") -> None:
        """Recursively extract elements from DOM nodes."""
        if not isinstance(node, dict):
            return
        
        node_type = node.get('type')
        if node_type != 1:  # Only process element nodes
            return
        
        tag_name = node.get('tagName', '').lower()
        attributes = node.get('attributes', {})
        
        # Check if this is a clickable element
        if self.is_clickable_element(tag_name, attributes):
            element_id = self.generate_element_id(node, path)
            selector = self.generate_css_selector(node, path)
            
            element_data = {
                'eid': element_id,
                'page_path': page_path,
                'page_dom_hash': dom_hash,
                'selector': selector,
                'tag': tag_name,
                'label': self.extract_element_label(node),
                'category': self.classify_element_category(tag_name, attributes),
                'text_content': self.extract_element_text(node),
                'x': None,  # Will be filled from interaction events
                'y': None,
                'width': None,
                'height': None,
                'org_id': org_id
            }
            
            elements.append(element_data)
            
            # Cache element for later reference
            self.element_cache[element_id] = element_data
        
        # Process children
        children = node.get('childNodes', [])
        for i, child in enumerate(children):
            child_path = f"{path}>{i}" if path else str(i)
            self._extract_elements_recursive(child, elements, page_path, dom_hash, org_id, child_path)
    
    def is_clickable_element(self, tag_name: str, attributes: Dict[str, Any]) -> bool:
        """Determine if an element is clickable."""
        clickable_tags = ['button', 'a', 'input', 'select', 'textarea']
        
        if tag_name in clickable_tags:
            return True
        
        # Check for click handlers or interactive roles
        if any(attr.startswith('on') for attr in attributes.keys()):
            return True
        
        role = attributes.get('role', '')
        if role in ['button', 'link', 'menuitem', 'tab']:
            return True
        
        # Check for common interactive classes
        class_name = attributes.get('class', '')
        if any(keyword in class_name.lower() for keyword in ['btn', 'button', 'click', 'link']):
            return True
        
        return False
    
    def extract_action_from_event(self, event: Dict[str, Any], org_id: int) -> Optional[Dict[str, Any]]:
        """Extract action from MouseInteraction event."""
        try:
            data = event.get('data', {})
            self.action_counter += 1
            
            action_data = {
                'action_id': f"{self.session_id}_action_{self.action_counter}",
                'session_id': str(self.session_id),
                'type': self.map_interaction_type(data.get('type')),
                'ts': datetime.fromtimestamp(event.get('timestamp', 0) / 1000),
                'x': data.get('x'),
                'y': data.get('y'),
                'page_path': self.get_current_page_path(),
                'page_dom_hash': self.current_page_hash,
                'element_id': self.find_element_at_position(data.get('x'), data.get('y')),
                'org_id': org_id
            }
            
            return action_data
            
        except Exception as e:
            logger.error(f"Error extracting action from event: {str(e)}")
            return None
    
    def extract_scroll_action(self, event: Dict[str, Any], org_id: int) -> Optional[Dict[str, Any]]:
        """Extract scroll action."""
        try:
            data = event.get('data', {})
            self.action_counter += 1
            
            return {
                'action_id': f"{self.session_id}_scroll_{self.action_counter}",
                'session_id': str(self.session_id),
                'type': 'scroll',
                'ts': datetime.fromtimestamp(event.get('timestamp', 0) / 1000),
                'x': data.get('x'),
                'y': data.get('y'),
                'page_path': self.get_current_page_path(),
                'page_dom_hash': self.current_page_hash,
                'org_id': org_id
            }
        except Exception as e:
            logger.error(f"Error extracting scroll action: {str(e)}")
            return None
    
    def extract_input_action(self, event: Dict[str, Any], org_id: int) -> Optional[Dict[str, Any]]:
        """Extract input action."""
        try:
            data = event.get('data', {})
            self.action_counter += 1
            
            return {
                'action_id': f"{self.session_id}_input_{self.action_counter}",
                'session_id': str(self.session_id),
                'type': 'input',
                'ts': datetime.fromtimestamp(event.get('timestamp', 0) / 1000),
                'value': data.get('text', ''),
                'page_path': self.get_current_page_path(),
                'page_dom_hash': self.current_page_hash,
                'element_id': self.find_element_by_id(data.get('id')),
                'org_id': org_id
            }
        except Exception as e:
            logger.error(f"Error extracting input action: {str(e)}")
            return None
    
    def extract_media_action(self, event: Dict[str, Any], org_id: int) -> Optional[Dict[str, Any]]:
        """Extract media interaction action."""
        try:
            data = event.get('data', {})
            self.action_counter += 1
            
            return {
                'action_id': f"{self.session_id}_media_{self.action_counter}",
                'session_id': str(self.session_id),
                'type': f"media_{data.get('type', 'unknown')}",
                'ts': datetime.fromtimestamp(event.get('timestamp', 0) / 1000),
                'page_path': self.get_current_page_path(),
                'page_dom_hash': self.current_page_hash,
                'element_id': self.find_element_by_id(data.get('id')),
                'org_id': org_id
            }
        except Exception as e:
            logger.error(f"Error extracting media action: {str(e)}")
            return None
    
    def extract_custom_event(self, event: Dict[str, Any], org_id: int) -> Optional[Dict[str, Any]]:
        """Extract custom event."""
        try:
            data = event.get('data', {})
            
            # Convert payload to JSON string if it exists
            payload = data.get('payload', {})
            payload_str = json.dumps(payload) if payload else None
            
            return {
                'cust_id': str(uuid.uuid4()),
                'session_id': str(self.session_id),
                'event_name': data.get('tag', 'custom_event'),
                'payload': payload_str,
                'ts': datetime.fromtimestamp(event.get('timestamp', 0) / 1000),
                'page_path': self.get_current_page_path(),
                'org_id': org_id
            }
        except Exception as e:
            logger.error(f"Error extracting custom event: {str(e)}")
            return None
    
    # Helper methods
    def get_user_agent_from_events(self) -> Optional[str]:
        """Extract user agent from events."""
        for event in self.events:
            if event.get('type') == 4:  # Meta events
                data = event.get('data', {})
                if data.get('tag') == 'userAgent':
                    return data.get('payload', {}).get('userAgent')
        return None
    
    def parse_user_agent(self, user_agent: str) -> Dict[str, Any]:
        """Parse user agent string for device information."""
        # Basic user agent parsing
        device_info = {
            'type': 'desktop',
            'os': 'unknown',
            'browser': 'unknown'
        }
        
        ua_lower = user_agent.lower()
        
        # Detect mobile
        if any(mobile in ua_lower for mobile in ['mobile', 'android', 'iphone', 'ipad']):
            device_info['type'] = 'mobile'
        
        # Detect OS
        if 'windows' in ua_lower:
            device_info['os'] = 'windows'
        elif 'mac' in ua_lower:
            device_info['os'] = 'macos'
        elif 'linux' in ua_lower:
            device_info['os'] = 'linux'
        elif 'android' in ua_lower:
            device_info['os'] = 'android'
        elif 'ios' in ua_lower or 'iphone' in ua_lower or 'ipad' in ua_lower:
            device_info['os'] = 'ios'
        
        # Detect browser
        if 'chrome' in ua_lower:
            device_info['browser'] = 'chrome'
        elif 'firefox' in ua_lower:
            device_info['browser'] = 'firefox'
        elif 'safari' in ua_lower:
            device_info['browser'] = 'safari'
        elif 'edge' in ua_lower:
            device_info['browser'] = 'edge'
        
        return device_info
    
    def generate_device_id(self, user_agent: Optional[str], device_info: Dict[str, Any]) -> str:
        """Generate a device ID from user agent and device info."""
        if not user_agent:
            return str(uuid.uuid4())
        
        # Create a hash of user agent for consistent device ID
        hash_obj = hashlib.md5(user_agent.encode('utf-8'))
        return f"device_{hash_obj.hexdigest()[:16]}"
    
    def extract_url_from_node(self, node: Dict[str, Any]) -> Optional[str]:
        """Extract URL from DOM node."""
        # Look for meta tags or current location
        def find_url_recursive(n):
            if not isinstance(n, dict):
                return None
            
            if n.get('tagName', '').lower() == 'meta':
                attrs = n.get('attributes', {})
                if attrs.get('property') == 'og:url':
                    return attrs.get('content')
            
            # Check children
            for child in n.get('childNodes', []):
                url = find_url_recursive(child)
                if url:
                    return url
            
            return None
        
        url = find_url_recursive(node)
        return url or "/"  # Default to root if no URL found
    
    def extract_title_from_node(self, node: Dict[str, Any]) -> Optional[str]:
        """Extract page title from DOM node."""
        def find_title_recursive(n):
            if not isinstance(n, dict):
                return None
            
            if n.get('tagName', '').lower() == 'title':
                # Get text content from children
                for child in n.get('childNodes', []):
                    if child.get('type') == 3:  # Text node
                        return child.get('textContent', '').strip()
            
            # Check children
            for child in n.get('childNodes', []):
                title = find_title_recursive(child)
                if title:
                    return title
            
            return None
        
        return find_title_recursive(node)
    
    def classify_page_template(self, path: str) -> str:
        """Classify page template based on path."""
        path_lower = path.lower()
        
        if any(keyword in path_lower for keyword in ['/product/', '/item/', '/p/']):
            return 'product'
        elif any(keyword in path_lower for keyword in ['/cart', '/basket']):
            return 'cart'
        elif any(keyword in path_lower for keyword in ['/checkout', '/payment']):
            return 'checkout'
        elif any(keyword in path_lower for keyword in ['/search', '/results']):
            return 'search'
        elif path_lower in ['/', '/home', '/index']:
            return 'home'
        else:
            return 'other'
    
    def classify_page_section(self, path: str) -> str:
        """Classify page section based on path."""
        path_lower = path.lower()
        
        if any(keyword in path_lower for keyword in ['/checkout', '/payment', '/cart']):
            return 'checkout'
        elif any(keyword in path_lower for keyword in ['/product', '/shop', '/catalog']):
            return 'shopping'
        elif any(keyword in path_lower for keyword in ['/about', '/contact', '/help']):
            return 'marketing'
        else:
            return 'general'
    
    def generate_element_id(self, node: Dict[str, Any], path: str) -> str:
        """Generate unique element ID."""
        attributes = node.get('attributes', {})
        
        # Use existing ID if available
        if 'id' in attributes:
            return f"elem_{attributes['id']}"
        
        # Use data-testid if available
        if 'data-testid' in attributes:
            return f"elem_{attributes['data-testid']}"
        
        # Generate from path and attributes
        tag_name = node.get('tagName', 'unknown')
        class_name = attributes.get('class', '')
        
        element_signature = f"{tag_name}_{path}_{class_name}"
        hash_obj = hashlib.md5(element_signature.encode('utf-8'))
        return f"elem_{hash_obj.hexdigest()[:12]}"
    
    def generate_css_selector(self, node: Dict[str, Any], path: str) -> str:
        """Generate CSS selector for element."""
        tag_name = node.get('tagName', '').lower()
        attributes = node.get('attributes', {})
        
        selector = tag_name
        
        if 'id' in attributes:
            selector += f"#{attributes['id']}"
        elif 'class' in attributes:
            classes = attributes['class'].replace(' ', '.')
            selector += f".{classes}"
        
        return selector
    
    def extract_element_label(self, node: Dict[str, Any]) -> Optional[str]:
        """Extract label/text from element."""
        # Check common label attributes
        attributes = node.get('attributes', {})
        
        for attr in ['aria-label', 'title', 'alt', 'placeholder']:
            if attr in attributes:
                return attributes[attr]
        
        # Extract text content
        return self.extract_element_text(node)
    
    def extract_element_text(self, node: Dict[str, Any]) -> Optional[str]:
        """Extract text content from element."""
        def get_text_recursive(n):
            if not isinstance(n, dict):
                return ""
            
            if n.get('type') == 3:  # Text node
                return n.get('textContent', '').strip()
            
            text_parts = []
            for child in n.get('childNodes', []):
                text_parts.append(get_text_recursive(child))
            
            return " ".join(text_parts).strip()
        
        text = get_text_recursive(node)
        return text if text else None
    
    def classify_element_category(self, tag_name: str, attributes: Dict[str, Any]) -> str:
        """Classify element category."""
        class_name = attributes.get('class', '').lower()
        
        if tag_name == 'button' or 'btn' in class_name or 'button' in class_name:
            if any(keyword in class_name for keyword in ['submit', 'primary', 'cta']):
                return 'CTA'
            return 'button'
        elif tag_name == 'a':
            if any(keyword in class_name for keyword in ['nav', 'menu']):
                return 'nav'
            return 'link'
        elif tag_name in ['input', 'textarea', 'select']:
            return 'form'
        else:
            return 'other'
    
    def map_interaction_type(self, rrweb_type: int) -> str:
        """Map rrweb interaction type to our action type."""
        type_mapping = {
            0: 'mouseup',
            1: 'mousedown', 
            2: 'click',
            3: 'contextmenu',
            4: 'dblclick',
            5: 'focus',
            6: 'blur',
            7: 'touchstart',
            8: 'touchmove',
            9: 'touchend'
        }
        return type_mapping.get(rrweb_type, 'unknown')
    
    def get_current_page_path(self) -> Optional[str]:
        """Get current page path from context."""
        if self.current_url:
            return urlparse(self.current_url).path
        return None
    
    def find_element_at_position(self, x: Optional[int], y: Optional[int]) -> Optional[str]:
        """Find element ID at given position (simplified implementation)."""
        # This is a simplified implementation
        # In a real scenario, you'd need to maintain element positions
        return None
    
    def find_element_by_id(self, node_id: Optional[int]) -> Optional[str]:
        """Find element by rrweb node ID."""
        # This would require maintaining a mapping of rrweb node IDs to element IDs
        return None 