"""TA Rankings — top gainers/losers."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_06_ta_rankings

ctx = get_context()
render_page_header("TA Rankings", ctx, section="Network")
if guard_data(ctx):
    tab_06_ta_rankings.render(ctx)
