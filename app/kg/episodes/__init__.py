"""Custom entity types for the Knowledge Graph using Graphiti."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

# Custom entity types following Graphiti documentation
# https://help.getzep.com/graphiti/graphiti/custom-entity-types

class User(BaseModel):
    """A user entity in the knowledge graph."""
    user_id: str = Field(..., description="Unique identifier for the user")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    first_seen: Optional[datetime] = Field(default=None, description="First time user was seen")
    last_seen: Optional[datetime] = Field(default=None, description="Last time user was active")
    plan: Optional[str] = Field(default=None, description="User's subscription plan")
    country: Optional[str] = Field(default=None, description="User's country")
    device_count: Optional[int] = Field(default=None, description="Number of devices used")


class Device(BaseModel):
    """A device entity in the knowledge graph."""
    device_id: str = Field(..., description="Unique identifier for the device")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    type: str = Field(..., description="Device type (mobile/desktop/tablet)")
    os: Optional[str] = Field(default=None, description="Operating system")
    browser: Optional[str] = Field(default=None, description="Browser name")
    screen_res: Optional[str] = Field(default=None, description="Screen resolution")
    ua_string: Optional[str] = Field(default=None, description="User agent string")


class Session(BaseModel):
    """A session entity in the knowledge graph."""
    session_id: str = Field(..., description="Unique identifier for the session")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    user_id: str = Field(default="anonymous", description="ID of the user who initiated the session")
    device_id: str = Field(default="unknown", description="ID of the device used in the session")
    start_ts: datetime = Field(..., description="Session start timestamp")
    end_ts: datetime = Field(..., description="Session end timestamp")
    duration: float = Field(..., description="Session duration in seconds")
    ip: Optional[str] = Field(default=None, description="IP address")
    geo: Optional[str] = Field(default=None, description="Geographic information as JSON string")
    is_authenticated: bool = Field(default=False, description="Whether user was authenticated")
    recording_id: Optional[int] = Field(default=None, description="Associated recording ID")


class Page(BaseModel):
    """A page template entity in the knowledge graph."""
    path: str = Field(..., description="URL path of the page")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    title: Optional[str] = Field(default=None, description="Page title")
    dom_hash: str = Field(..., description="SHA-1 hash of DOM structure")
    template: Optional[str] = Field(default=None, description="Page template type (home/product/cart/etc)")
    section: Optional[str] = Field(default=None, description="Page section (marketing/checkout/etc)")


class PageView(BaseModel):
    """A page view instance entity in the knowledge graph."""
    pv_id: str = Field(..., description="Unique identifier for the page view")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    session_id: str = Field(..., description="Session ID this page view belongs to")
    page_path: str = Field(..., description="Path of the page being viewed")
    page_dom_hash: str = Field(..., description="DOM hash of the page being viewed")
    timestamp: datetime = Field(..., description="When the page view occurred")
    order_in_session: int = Field(..., description="Order of this page view in the session")
    referrer: Optional[str] = Field(default=None, description="Referrer URL")
    viewport_h: Optional[int] = Field(default=None, description="Viewport height")
    viewport_w: Optional[int] = Field(default=None, description="Viewport width")


class Element(BaseModel):
    """An interactive element entity in the knowledge graph."""
    eid: str = Field(..., description="Unique identifier for the element")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    page_path: str = Field(..., description="Path of the page containing this element")
    page_dom_hash: str = Field(..., description="DOM hash of the page containing this element")
    selector: str = Field(..., description="CSS selector for the element")
    label: Optional[str] = Field(default=None, description="Element label or text")
    tag: str = Field(..., description="HTML tag name")
    category: Optional[str] = Field(default=None, description="Element category (CTA/nav/form/button/link)")
    synonyms: Optional[List[str]] = Field(default=None, description="Alternative names for the element")
    x: Optional[int] = Field(default=None, description="X coordinate on page")
    y: Optional[int] = Field(default=None, description="Y coordinate on page")
    width: Optional[int] = Field(default=None, description="Element width")
    height: Optional[int] = Field(default=None, description="Element height")
    text_content: Optional[str] = Field(default=None, description="Text content of the element")


class Action(BaseModel):
    """A user action entity in the knowledge graph."""
    action_id: str = Field(..., description="Unique identifier for the action")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    session_id: str = Field(..., description="Session ID where action occurred")
    element_id: Optional[str] = Field(default=None, description="Element ID that was acted upon")
    type: str = Field(..., description="Action type (click/input/scroll/hover)")
    ts: datetime = Field(..., description="When the action occurred")
    x: Optional[int] = Field(default=None, description="X coordinate of action")
    y: Optional[int] = Field(default=None, description="Y coordinate of action")
    value: Optional[str] = Field(default=None, description="Value for input actions")
    page_path: Optional[str] = Field(default=None, description="Page path where action occurred")
    page_dom_hash: Optional[str] = Field(default=None, description="DOM hash of page where action occurred")


class CustomEvent(BaseModel):
    """A custom semantic event entity in the knowledge graph."""
    cust_id: str = Field(..., description="Unique identifier for the custom event")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    session_id: str = Field(..., description="Session ID where event occurred")
    event_name: str = Field(..., description="Event name (add_to_cart, checkout_started, etc)")
    payload: Optional[str] = Field(default=None, description="Event payload data as JSON string")
    ts: datetime = Field(..., description="When the event occurred")
    triggered_by_action_id: Optional[str] = Field(default=None, description="Action ID that triggered this event")
    page_path: Optional[str] = Field(default=None, description="Page path where event occurred")


class NetworkRequest(BaseModel):
    """A network request entity in the knowledge graph."""
    req_id: str = Field(..., description="Unique identifier for the network request")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    session_id: str = Field(..., description="Session ID where request occurred")
    url: str = Field(..., description="Request URL")
    method: str = Field(..., description="HTTP method")
    status: Optional[int] = Field(default=None, description="HTTP status code")
    latency_ms: Optional[float] = Field(default=None, description="Request latency in milliseconds")
    ts: datetime = Field(..., description="When the request occurred")
    triggered_by_action_id: Optional[str] = Field(default=None, description="Action ID that triggered this request")
    page_path: Optional[str] = Field(default=None, description="Page path where request occurred")


class ErrorEvent(BaseModel):
    """An error event entity in the knowledge graph."""
    err_id: str = Field(..., description="Unique identifier for the error event")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    session_id: str = Field(..., description="Session ID where error occurred")
    message: str = Field(..., description="Error message")
    stack: Optional[str] = Field(default=None, description="Error stack trace")
    severity: str = Field(..., description="Error severity (error/warning/info)")
    ts: datetime = Field(..., description="When the error occurred")
    page_path: Optional[str] = Field(default=None, description="Page path where error occurred")
    page_dom_hash: Optional[str] = Field(default=None, description="DOM hash of page where error occurred")


class PerformanceMetric(BaseModel):
    """A performance metric entity in the knowledge graph."""
    metric_id: str = Field(..., description="Unique identifier for the metric")
    org_id: int = Field(..., description="Organization ID for multi-tenant isolation")
    session_id: str = Field(..., description="Session ID where metric was measured")
    pageview_id: str = Field(..., description="Page view ID where metric was measured")
    metric_name: str = Field(..., description="Metric name (LCP/FID/CLS/etc)")
    value: float = Field(..., description="Metric value")
    ts: datetime = Field(..., description="When the metric was measured")
    page_path: Optional[str] = Field(default=None, description="Page path where metric was measured")


# Dictionary of all entity types for Graphiti
ENTITY_TYPES = {
    "User": User,
    "Device": Device,
    "Session": Session,
    "Page": Page,
    "PageView": PageView,
    "Element": Element,
    "Action": Action,
    "CustomEvent": CustomEvent,
    "NetworkRequest": NetworkRequest,
    "ErrorEvent": ErrorEvent,
    "PerformanceMetric": PerformanceMetric,
}

__all__ = [
    "User",
    "Device", 
    "Session",
    "Page",
    "PageView",
    "Element",
    "Action",
    "CustomEvent",
    "NetworkRequest",
    "ErrorEvent",
    "PerformanceMetric",
    "ENTITY_TYPES",
] 