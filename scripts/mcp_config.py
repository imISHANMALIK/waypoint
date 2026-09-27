"""Print a ready-to-paste MCP configuration for this exact checkout."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
print(json.dumps({"mcpServers": {"waypoint": {
    "command": str(root/".venv/bin/python"),
    "args": [str(root/"backend/mcp_server.py")],
    "env": {"WAYPOINT_API_URL": "http://127.0.0.1:8000"}
}}}, indent=2))
