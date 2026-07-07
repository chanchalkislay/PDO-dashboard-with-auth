"""Sales Volumes — RO-level volume export."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import guard_data, render_page_header
import tab_11_sales_volumes

ctx = get_context()
render_page_header("Sales Volumes", ctx, section="Operations")
if guard_data(ctx):
    tab_11_sales_volumes.render(ctx)
