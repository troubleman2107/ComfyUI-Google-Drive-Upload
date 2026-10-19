"""Standalone Google Drive Upload nodes for ComfyUI."""
from .nodes.node_google_drive_upload import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .google_drive_routes import register_drive_routes
from server import PromptServer

register_drive_routes(PromptServer.instance.routes)
WEB_DIRECTORY = "./js"
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
