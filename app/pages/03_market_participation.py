"""Market Participation & Network Effectiveness."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_03_market_participation

ctx = get_context()
render_page_header("Market Participation", ctx, section="Network")
if guard_data(ctx):
    tab_03_market_participation.render(ctx)
