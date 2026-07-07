"""Alternate fuels — CNG / CBG."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_24_alt_fuel

ctx = get_context()
render_page_header("Alternate Fuels (CNG/CBG)", ctx, section="Assets & Infra")
tab_24_alt_fuel.render(ctx)
