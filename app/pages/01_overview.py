"""Overview — KPI cards + OMC breakdown."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_01_overview

ctx = get_context()
render_page_header("Overview", ctx, section="Executive")
if guard_data(ctx):
    tab_01_overview.render(ctx)
