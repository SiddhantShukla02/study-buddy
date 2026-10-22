# Friction log

## 1. Installing the SDK pulled in a breaking major version
- **Task:** Install the MCP Python SDK and run the standard FastMCP example.
- **Steps:** `pip install mcp`, then `from mcp.server.fastmcp import FastMCP`.
- **Expected:** The import works.
- **Actual:** mcp 2.x installed, and the import failed because `FastMCP` was renamed `MCPServer`.
- **Severity:** Medium (clear error message, but it blocks new users following older examples).
- **Workaround:** Pinned `mcp>=1.23,<2`.
- **Suggestion:** Show the version pin prominently in quickstarts until examples are updated.

## 2. `call_tool` returns different shapes per tool
- **Task:** Call tools in-process and read the results.
- **Expected:** One consistent return type.
- **Actual:** Dict-returning tools gave a list of TextContent with JSON text; list-returning tools gave a
  `(content, structured)` tuple.
- **Severity:** Low to medium.
- **Workaround:** A small normalizing step that parses either shape.
- **Suggestion:** Document the return shapes, or return a single consistent type.

## 3. System-wide pip install failed
- **Task:** Install into the system Python.
- **Actual:** pip could not uninstall a distro-managed PyJWT and aborted.
- **Severity:** Low.
- **Workaround:** Used a virtualenv.
- **Suggestion:** Recommend a virtualenv in the install docs.
