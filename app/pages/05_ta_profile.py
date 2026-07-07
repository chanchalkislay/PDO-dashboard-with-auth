"""TA Profile — PPT-format per-RO grid."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_05_ta_profile

ctx = get_context()
render_page_header("TA Profile (PPT)", ctx, section="Trading Area")
if guard_data(ctx):
    tab_05_ta_profile.render(ctx)
