"""Trend Analysis Historical — MS/HSD share FY20→FY26."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_07_trend

ctx = get_context()
render_page_header("Trend Analysis Historical", ctx, section="Executive")
if guard_data(ctx):
    tab_07_trend.render(ctx)
