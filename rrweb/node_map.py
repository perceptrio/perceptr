"""
Build a node_id -> human-readable label map from rrweb FullSnapshot (type 2).

Correlates with incremental events: click/focus/scroll/input carry node ids
that refer to this snapshot, so we can emit e.g. "user click on button \"Get started\"".

Also detects element interactivity (href, role, tabindex, inline handlers, etc.)
to help distinguish bugs from UX issues when a click has no visible effect.
"""

from __future__ import annotations

from typing import Optional


# rrweb node type: 2 = Element
NODE_TYPE_ELEMENT = 2
NODE_TYPE_TEXT = 3

# Max chars for text label (token-saving)
MAX_LABEL_LEN = 48

# ── Interactivity detection ──────────────────────────────────────────────────

# Tags that are inherently interactive (users expect them to do something)
_INTERACTIVE_TAGS = frozenset[str](
    {
        "a",
        "button",
        "input",
        "select",
        "textarea",
        "summary",
        "details",
        "option",
        "label",
    }
)

# ARIA roles that indicate interactive widgets
_INTERACTIVE_ROLES = frozenset[str](
    {
        "button",
        "link",
        "tab",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "checkbox",
        "radio",
        "switch",
        "combobox",
        "slider",
        "spinbutton",
        "searchbox",
        "textbox",
        "option",
        "treeitem",
        "gridcell",
    }
)

# Inline event handler attributes (present when framework uses inline binding)
_EVENT_HANDLER_ATTRS = frozenset[str](
    {
        "onclick",
        "onmousedown",
        "onmouseup",
        "ontouchstart",
        "ontouchend",
        "onkeydown",
        "onkeypress",
        "onkeyup",
    }
)


def _is_interactive(node: dict) -> bool:
    """Determine if an element is expected to respond to clicks.

    Checks intrinsic tag interactivity, ARIA roles, href, tabindex,
    inline event handlers, and common data-* conventions.

    Note: cannot detect addEventListener (React/Vue synthetic events),
    so False means "no *visible* trigger" rather than "definitely inert".
    """
    tag = (node.get("tagName") or "").lower()
    attrs = node.get("attributes") or {}

    # Inherently interactive tags
    if tag in _INTERACTIVE_TAGS:
        return True

    # Has href (makes any element navigable)
    if attrs.get("href"):
        return True

    # Interactive ARIA role
    role = (attrs.get("role") or "").lower()
    if role in _INTERACTIVE_ROLES:
        return True

    # Made focusable via tabindex
    if "tabindex" in attrs:
        try:
            if int(attrs["tabindex"]) >= 0:
                return True
        except (ValueError, TypeError):
            pass

    # Inline event handlers
    if any(k.lower() in _EVENT_HANDLER_ATTRS for k in attrs):
        return True

    # data-* attributes suggesting interactivity
    for key in attrs:
        if isinstance(key, str) and key.startswith("data-"):
            if any(
                hint in key for hint in ("click", "action", "href", "toggle", "dismiss")
            ):
                return True

    return False


def _extract_labels(node: dict, depth: int = 5) -> list[str]:
    """
    Recursively extract values of aria-label, placeholder, name, and textContent
    from node and its children if present. Returns a list of label strings.
    """
    labels = []
    attrs = node.get("attributes") or {}

    # Try aria-label, placeholder, name on this node
    for k in ("aria-label", "placeholder", "name", "type", "value"):
        v = attrs.get(k)
        if v:
            labels.append(f"{k}:{str(v).strip()}")

    # Try direct textContent on this node (for text nodes or attribute)
    if "textContent" in node:
        text = node.get("textContent")
        if isinstance(text, str) and text.strip() and text != "SCRIPT_PLACEHOLDER":
            labels.append(" ".join(text.strip().split())[:MAX_LABEL_LEN])
    # Or direct text child node for element
    for child in node.get("childNodes", []):
        if child.get("type") == NODE_TYPE_TEXT:
            t = (child.get("textContent") or "").strip()
            if t and t != "SCRIPT_PLACEHOLDER":
                labels.append(" ".join(t.split())[:MAX_LABEL_LEN])
        elif child.get("type") == NODE_TYPE_ELEMENT and depth > 0:
            # Recursively get labels from child elements with max of 5 levels deep
            child_labels = _extract_labels(child, depth - 1)
            labels.extend(child_labels)
    return labels


def _label_for_element(node: dict) -> str:
    """
    One-line label for an element: tag + concatenated descriptors.
    Gets aria-label, placeholder, name, textContent from self and children.
    """
    tag = (node.get("tagName") or "unknown").lower()
    attrs = node.get("attributes") or {}

    # Gather labels from element and its children
    labels = _extract_labels(node)
    label = " | ".join([l[:MAX_LABEL_LEN] for l in labels if l]) if labels else ""

    # Fallback to id if nothing else found
    if not label and attrs.get("id"):
        label = attrs.get("id")
    if label:
        return f'{tag} "{label}"'
    return tag


def build_node_map(snapshot_node: dict) -> dict[int, str]:
    """
    Walk full snapshot DOM tree and build node_id -> human-readable label.

    Only element nodes (type 2) with an id are stored. Idempotent for same input.
    """
    out: dict[int, str] = {}

    def walk(n: dict) -> None:
        node_type = n.get("type")
        node_id = n.get("id")
        if node_type == NODE_TYPE_ELEMENT and node_id is not None:
            out[node_id] = _label_for_element(n)
        for child in n.get("childNodes", []):
            walk(child)

    walk(snapshot_node)
    return out


def build_node_maps(
    snapshot_node: dict,
) -> tuple[dict[int, str], dict[int, bool]]:
    """Build BOTH the label map and the interactivity map in a single walk.

    Returns:
        (node_map, interactive_map) where interactive_map[node_id] = True
        means the element has intrinsic interactive affordances (tag, role,
        href, tabindex, inline handler, etc.).
    """
    labels: dict[int, str] = {}
    interactive: dict[int, bool] = {}

    def walk(n: dict) -> None:
        node_type = n.get("type")
        node_id = n.get("id")
        if node_type == NODE_TYPE_ELEMENT and node_id is not None:
            labels[node_id] = _label_for_element(n)
            interactive[node_id] = _is_interactive(n)
        for child in n.get("childNodes", []):
            walk(child)

    walk(snapshot_node)
    return labels, interactive


def resolve_node(node_map: dict[int, str], node_id: Optional[int]) -> str:
    """Resolve node id to label; fallback to 'element #id'."""
    if node_id is None:
        return "unknown element"
    return node_map.get(node_id, f"element #{node_id}")


def apply_node_to_map(
    node_map: dict[int, str],
    node: dict,
    interactive_map: dict[int, bool] | None = None,
) -> None:
    """
    Merge a single node and its descendants into node_map (e.g. from mutation adds).
    Used to keep node_map in sync with DOM after incremental mutations.

    If interactive_map is provided, also updates interactivity info.
    """
    node_type = node.get("type")
    node_id = node.get("id")
    if node_type == NODE_TYPE_ELEMENT and node_id is not None:
        node_map[node_id] = _label_for_element(node)
        if interactive_map is not None:
            interactive_map[node_id] = _is_interactive(node)
    for child in node.get("childNodes", []):
        apply_node_to_map(node_map, child, interactive_map)


def remove_from_map(node_map: dict[int, str], node_ids: list[int]) -> None:
    """Remove node ids from map (e.g. from mutation removes)."""
    for nid in node_ids:
        node_map.pop(nid, None)
