"""XtraPower — ITPS coverage, transacting, conversion, red flags."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_13_xtrapower

ctx = get_context()
render_page_header("XtraPower", ctx, section="Operations")
tab_13_xtrapower.render(ctx)
