from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP

from mcp_custom import register_tools
from config import load_settings, default_config_path
from config import Settings
from storage.session_manager import SessionLifecycleManager
from utils.logging import get_logger

logger = get_logger()


def create_server(cfg: Settings) -> FastMCP:
    """
    Creates the MCP server and registers tools
    """

    runtime_ctx = cfg

    @asynccontextmanager
    async def session_lifespan(
        server: FastMCP,
    ) -> AsyncIterator[SessionLifecycleManager]:
        """Manage session lifecycle with type-safe context."""
        # Initialize on startup
        logger.info("Enable session lifespan manager")
        session_manager = SessionLifecycleManager(
            artifacts_root=cfg.project.outputs_dir,
            cache_root=cfg.local_mcp_server.server_cache_dir,
            enable_cleanup=True,
        )
        try:
            yield session_manager
        finally:
            # Cleanup on shutdown
            session_manager.cleanup_expired_sessions()

    server = FastMCP(
        name=cfg.local_mcp_server.server_name,
        stateless_http=cfg.local_mcp_server.stateless_http,
        json_response=cfg.local_mcp_server.json_response,
        lifespan=session_lifespan,
    )

    # Pass runtime_ctx to register_tools so each tool can access cfg
    register_tools.register(server, runtime_ctx)

    return server


def main():
    cfg = load_settings(default_config_path())
    server = create_server(cfg)
    server.settings.host = cfg.local_mcp_server.connect_host
    server.settings.port = cfg.local_mcp_server.port
    server.run(transport=cfg.local_mcp_server.server_transport)


if __name__ == "__main__":
    main()
