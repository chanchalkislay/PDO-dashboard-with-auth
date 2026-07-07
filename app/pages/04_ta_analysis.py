"""Trading-Area Analysis — per-TA grid."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_04_ta_analysis

ctx = get_context()
render_page_header("Trading-Area Analysis", ctx, section="Network")
if guard_data(ctx):
    tab_04_ta_analysis.render(ctx)
