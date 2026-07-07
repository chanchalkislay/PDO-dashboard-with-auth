"""Market Share — share by RSA, District, COM, Highway."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_02_market_share

ctx = get_context()
render_page_header("Market Share", ctx, section="Executive")
if guard_data(ctx):
    tab_02_market_share.render(ctx)
