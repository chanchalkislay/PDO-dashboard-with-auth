"""Swagat Monitoring — extended TA, XP conversion, MoU."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_18_swagat

ctx = get_context()
render_page_header("Swagat Monitoring", ctx, section="Programmes")
tab_18_swagat.render(ctx)
