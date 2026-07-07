"""Lube Sales MIS."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_23_lube

ctx = get_context()
render_page_header("Lube Sales", ctx, section="Operations")
tab_23_lube.render(ctx)
