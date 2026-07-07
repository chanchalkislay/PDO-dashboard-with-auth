"""Commissioning pipeline — LOI register."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_22_commissioning

ctx = get_context()
render_page_header("Commissioning Pipeline", ctx, section="Assets & Infra")
tab_22_commissioning.render(ctx)
