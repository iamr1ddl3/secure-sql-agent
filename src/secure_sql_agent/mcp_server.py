"""MCP transport: tool `query_bank_data`. Same service, same protection as the HTTP API.

Run: python -m secure_sql_agent.mcp_server   (stdio)   or with --http for streamable HTTP.
HTTP binds MCP_HOST:MCP_PORT (default 127.0.0.1:8000); the Docker image sets MCP_HOST=0.0.0.0.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache

from mcp.server.mcpserver import MCPServer  # MCP Python SDK v2 (FastMCP was renamed)

from .contracts import DelegationHop, QueryRequest
from .service import QueryService, build_service

from . import __version__

mcp = MCPServer("secure-sql-agent", version=__version__)


@lru_cache
def _service() -> QueryService:
    return build_service()


@mcp.tool()
def query_bank_data(question: str, identity: str, on_behalf_of_chain: list[DelegationHop] | None = None,
                    max_rows: int = 100) -> dict:
    """Answer a plain-English question over the bank data as the user in `identity` (a signed JWT).

    Access is enforced by the database as that user. Returns the query_bank_data v1 response
    (see interface/query_bank_data.v1.schema.json).
    """
    req = QueryRequest(question=question, identity=identity, on_behalf_of_chain=on_behalf_of_chain,
                       max_rows=max_rows)
    return _service().handle(req).model_dump(mode="json")


if __name__ == "__main__":
    if "--http" in sys.argv:
        # The SDK binds 127.0.0.1 by default, which is unreachable from outside a container.
        mcp.run(transport="streamable-http", host=os.environ.get("MCP_HOST", "127.0.0.1"),
                port=int(os.environ.get("MCP_PORT", "8000")))
    else:
        mcp.run(transport="stdio")
