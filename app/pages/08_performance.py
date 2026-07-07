"""Performance — CY vs LY OMC comparison."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_08_performance

ctx = get_context()
render_page_header("Performance (CY vs LY)", ctx, section="Executive")
if guard_data(ctx):
    tab_08_performance.render(ctx)
