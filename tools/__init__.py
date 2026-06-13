"""
tools/ — OPTIONAL external capabilities (network / provider-backed).

Importing this package registers web, image, and MCP tools into core.toolbelt.
It lives OUTSIDE core/ on purpose: core stays offline and provider-agnostic, and
these tools are only activated when something (the server) imports `tools`.

    import tools   # noqa: F401  -> web_search, web_fetch, generate_image, mcp_call now available
"""
from . import web        # noqa: F401
from . import image      # noqa: F401
from . import mcp        # noqa: F401
from . import safety     # noqa: F401
from . import vision     # noqa: F401
