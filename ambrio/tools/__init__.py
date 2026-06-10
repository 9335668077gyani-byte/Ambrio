# ambrio/tools/__init__.py
"""Tool implementations — each module self-registers via @register_tool."""
# Tools are imported lazily by executor._dispatch_tool on first use.
# Add new tools by creating a module here and decorating with @register_tool.
