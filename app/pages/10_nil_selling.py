"""Nil Selling — NIL / About to Go Nil / Revivals."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_10_nil_selling

ctx = get_context()
render_page_header("Nil Selling", ctx, section="Operations")
tab_10_nil_selling.render(ctx)
