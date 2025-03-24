event_types = {
    0: "DomContentLoaded",
    1: "Load",
    2: "FullSnapshot",
    3: "IncrementalSnapshot",
    4: "Meta",
    5: "Custom",
    6: "Plugin",
}

incremental_snapshot_event_source = {
    0: "Mutation",
    1: "MouseMove",
    2: "MouseInteraction",
    3: "Scroll",
    4: "ViewportResize",
    5: "Input",
    6: "TouchMove",
    7: "MediaInteraction",
    8: "StyleSheetRule",
    9: "CanvasMutation",
    10: "Font",
    11: "Log",
    12: "Drag",
    13: "StyleDeclaration",
    14: "Selection",
    15: "AdoptedStyleSheet",
    16: "CustomElement",
}

node_types = {
    0: "Document",
    1: "DocumentType",
    2: "Element",
    3: "Text",
    4: "CDATA",
    5: "Comment",
}

mouse_interaction_types = {
    0: "MouseUp",
    1: "MouseDown",
    2: "Click",
    3: "ContextMenu",
    4: "DblClick",
    5: "Focus",
    6: "Blur",
    7: "TouchStart",
    8: "TouchMove_Departed",
    9: "TouchEnd",
    10: "TouchCancel",
}

media_interaction_types = {
    0: "Play",
    1: "Pause",
    2: "Seeked",
    3: "VolumeChange",
    4: "RateChange",
}

pointer_types = {
    0: "Mouse",
    1: "Pen",
    2: "Touch",
}

canvas_context_types = {
    0: "2D",
    1: "WebGL",
    2: "WebGL2",
}
