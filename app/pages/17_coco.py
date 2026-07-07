"""COCO Management — work orders + sales monitoring."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_17_coco

ctx = get_context()
render_page_header("COCO Management", ctx, section="Programmes")
tab_17_coco.render(ctx)
