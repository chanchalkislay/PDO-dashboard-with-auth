"""REMM — rent payment and lease monitoring."""
import bootstrap  # noqa: F401
from context import get_context
from components.layout import render_page_header
import tab_21_remm

ctx = get_context()
render_page_header("REMM — Rent & Lease", ctx, section="Assets & Infra")
tab_21_remm.render(ctx)
