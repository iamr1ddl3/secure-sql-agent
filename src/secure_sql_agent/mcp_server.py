"""MCP transport: tool `query_bank_data`. Same service, same protection as the HTTP API.

Run: python -m secure_sql_agent.mcp_server   (stdio)   or with --http for streamable HTTP.
"""
from __future__ import annotations

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
    mcp.run(transport="streamable-http" if "--http" in sys.argv else "stdio")
