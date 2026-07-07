"""Notional Loss/Gain — IOCL notional by RSA + TA movers."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_09_notional

ctx = get_context()
render_page_header("Notional Loss/Gain", ctx, section="Operations")
if guard_data(ctx):
    tab_09_notional.render(ctx)
