"""RO Benchmarking — IOCL RO vs TA leader."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_15_benchmarking

ctx = get_context()
render_page_header("RO Benchmarking", ctx, section="Network")
if guard_data(ctx):
    tab_15_benchmarking.render(ctx)
