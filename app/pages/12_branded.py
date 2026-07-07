"""Branded — XP95/XP100/XG analytics."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_12_branded

ctx = get_context()
render_page_header("Branded", ctx, section="Operations")
if guard_data(ctx):
    tab_12_branded.render(ctx)
