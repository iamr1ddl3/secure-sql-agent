"""Smoke test: connect to a running MCP server over streamable HTTP and check it lists query_bank_data.

Usage: python scripts/mcp_smoke.py [url]   (default http://localhost:8001/mcp)
"""
import asyncio
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main(url: str) -> None:
    async with streamable_http_client(url) as (read, write, *_), ClientSession(read, write) as session:
        info = await session.initialize()
        tools = [t.name for t in (await session.list_tools()).tools]
    print(f"{info.server_info.name} {info.server_info.version}: {tools}")
    assert tools == ["query_bank_data"], tools


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001/mcp"))
