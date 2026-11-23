"""Connectors: accounts and external tool servers the user plugs into AIVA from the dashboard.

* :class:`GmailConnector` — Gmail over IMAP/SMTP with a Google *App Password*
  (2-minute setup, no Google Cloud project needed).
* :class:`MCPManager` — any Model Context Protocol server (stdio command or HTTP
  URL), e.g. Playwright browser automation, Notion, GitHub, filesystem… Their tools
  appear to the brain as an extra skill category.
"""

from .gmail import GmailConnector
from .mcp import MCPManager
from .registry import ConnectorRegistry

__all__ = ["ConnectorRegistry", "GmailConnector", "MCPManager"]
