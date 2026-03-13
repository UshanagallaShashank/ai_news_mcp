"""
Standalone MCP Server Runner
=============================

Run the MCP server as a standalone process — no FastAPI, no Telegram needed.
This makes it reusable in ANY project.

Usage:
    # From the API/ directory:
    python -m mcp_server                    # default: stdio transport
    python -m mcp_server --transport sse    # SSE transport on port 8001
    python -m mcp_server --port 9000        # Custom port for SSE

Add to Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "ai-news": {
          "command": "python",
          "args": ["-m", "mcp_server"],
          "cwd": "/path/to/MCP-news/API"
        }
      }
    }

Add to Cursor (.cursor/mcp.json):
    {
      "mcpServers": {
        "ai-news": {
          "command": "python",
          "args": ["-m", "mcp_server"],
          "cwd": "/path/to/MCP-news/API"
        }
      }
    }

Environment variables needed:
    GOOGLE_API_KEY    — Only needed if you use the ADK agent (/ainews)
                        Not required for pure MCP tool usage.
"""

import argparse
import logging
import sys
import os

# Make sure the API/ directory is on the path when running as a module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from mcp_server.server import mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="AI News MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport type: stdio (for Claude Desktop/Cursor) or sse (for HTTP clients)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port number for SSE transport (default: 8001)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        # stdio = Claude Desktop / Cursor style (subprocess communication)
        logging.info("Starting MCP server with stdio transport")
        mcp.run(transport="stdio")
    else:
        # SSE = HTTP-based, for web clients or other projects calling over network
        logging.info(f"Starting MCP server with SSE transport on {args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
