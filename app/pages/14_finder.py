"""Finder & Reports — RO/TA ranking + bulk downloads."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_14_finder

ctx = get_context()
render_page_header("Finder & Reports", ctx, section="Tools")
if guard_data(ctx):
    tab_14_finder.render(ctx)
