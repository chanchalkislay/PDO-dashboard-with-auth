"""Shared dashboard context — sidebar state → filtered frames → ctx dict."""
from __future__ import annotations

import streamlit as st
import pandas as pd

from sidebar import SidebarState, render_sidebar


def _apply_filters(df, state: SidebarState):
    m = pd.Series(True, index=df.index)
    if state.sel_dist:
        m &= df.district.isin(state.sel_dist)
    if state.sel_rsa:
        m &= df.rsa_code.isin(state.sel_rsa)
    if state.sel_com:
        m &= df.com.isin(state.sel_com)
    if state.sel_hwytype:
        m &= df.hwy_type.isin(state.sel_hwytype)
    if state.sel_hwyno:
        m &= df.highway_no.isin(state.sel_hwyno)
    return df[m]


def _filt_note(state: SidebarState) -> str:
    active = [f for f, on in [
        (f"District={','.join(state.sel_dist)}", state.sel_dist),
        (f"RSA×{len(state.sel_rsa)}", state.sel_rsa),
        (f"COM={','.join(state.sel_com)}", state.sel_com),
        (f"HwyType={','.join(state.sel_hwytype)}", state.sel_hwytype),
        (f"HwyNo×{len(state.sel_hwyno)}", state.sel_hwyno),
    ] if on]

    if state.multi_fy_mode:
        base = (f"**{state.product}** · Multi-FY period: **{state.period_lbl}**"
                + ("  ·  " + " · ".join(active) if active else "  ·  whole DO"))
    else:
        base = (f"**{state.product}** · CY **{state.cy}** vs LY **{state.ly or '—'}** "
                f"· period **{state.period_lbl}**"
                + ("  ·  " + " · ".join(active) if active else "  ·  whole DO"))
    return base


@st.cache_data(show_spinner=False)
def _compute_period_frames(
    product: str,
    cy: str,
    ly: str | None,
    months_tuple: tuple,
    multi_fy_mode: bool,
    cy_pairs_tuple: tuple,
    ly_pairs_tuple: tuple,
    sel_dist: tuple,
    sel_rsa: tuple,
    sel_com: tuple,
    sel_hwytype: tuple,
    sel_hwyno: tuple,
):
    """Cache keyed by filter selections; loaders are cached separately in core."""
    from core import load_monthly, load_branded

    monthly = load_monthly()
    branded = load_branded()

    state = SidebarState(
        product=product,
        cy=cy,
        ly=ly,
        ptype="",
        months=months_tuple,
        period_lbl="",
        multi_fy_mode=multi_fy_mode,
        cy_pairs=frozenset(cy_pairs_tuple),
        ly_pairs=frozenset(ly_pairs_tuple),
        sel_dist=sel_dist,
        sel_rsa=sel_rsa,
        sel_com=sel_com,
        sel_hwytype=sel_hwytype,
        sel_hwyno=sel_hwyno,
        districts=(),
        rsa_labels={},
        coms=(),
        hwy_nums=(),
    )

    scope = _apply_filters(monthly, state)
    branded_scope = _apply_filters(branded, state)
    months = list(months_tuple)
    cy_pairs = set(cy_pairs_tuple)
    ly_pairs = set(ly_pairs_tuple)

    if multi_fy_mode:
        if cy_pairs:
            fymi_s = scope.fy_code + "_" + scope.month_index.astype(str)
            cy_keys = {f"{fy}_{mi}" for fy, mi in cy_pairs}
            ly_keys = {f"{fy}_{mi}" for fy, mi in ly_pairs}
            cy_f = scope[fymi_s.isin(cy_keys) & (scope["product"] == product)]
            ly_f = scope[fymi_s.isin(ly_keys) & (scope["product"] == product)]

            b_fymi = branded_scope.fy_code + "_" + branded_scope.month_index.astype(str)
            b_cy = branded_scope[b_fymi.isin(cy_keys) & (branded_scope["product"] == product)]
            b_ly = branded_scope[b_fymi.isin(ly_keys) & (branded_scope["product"] == product)]
        else:
            cy_f = scope.iloc[0:0]
            ly_f = scope.iloc[0:0]
            b_cy = branded_scope.iloc[0:0]
            b_ly = branded_scope.iloc[0:0]
    else:
        cy_f = scope[(scope.fy_code == cy) & (scope["product"] == product)
                     & (scope.month_index.isin(months))]
        ly_f = (scope[(scope.fy_code == ly) & (scope["product"] == product)
                      & (scope.month_index.isin(months))]
                if ly else scope.iloc[0:0])

        b_cy = branded_scope[(branded_scope.fy_code == cy)
                             & (branded_scope["product"] == product)
                             & (branded_scope.month_index.isin(months))]
        b_ly = (branded_scope[(branded_scope.fy_code == ly)
                              & (branded_scope["product"] == product)
                              & (branded_scope.month_index.isin(months))]
                if ly else branded_scope.iloc[0:0])

    return cy_f, ly_f, scope, branded_scope, b_cy, b_ly


def build_context(monthly, ro_master, ta_dim, branded, fys, TA_NAME) -> dict:
    """Render sidebar, compute frames, store and return the shared ctx dict."""
    state = render_sidebar(ro_master, fys)

    cy_f, ly_f, scope, branded_scope, b_cy, b_ly = _compute_period_frames(
        state.product,
        state.cy,
        state.ly,
        state.months,
        state.multi_fy_mode,
        tuple(state.cy_pairs),
        tuple(state.ly_pairs),
        state.sel_dist,
        state.sel_rsa,
        state.sel_com,
        state.sel_hwytype,
        state.sel_hwyno,
    )

    ro_scope = _apply_filters(ro_master, state)
    
    # Apply Dealer role restrictions to dataframes
    user = st.session_state.get("user")
    if user and user.get("role") == "dealer":
        u_ro = user.get("ro_code")
        if u_ro:
            # Split and clean RO codes list
            u_ro_list = [str(r.strip()) for r in u_ro.split(",") if r.strip()]
            dealer_ros = ro_master[ro_master.sap_code.astype(str).isin(u_ro_list)]
            if not dealer_ros.empty:
                # Find all unique TA codes for these ROs
                u_tas = dealer_ros.ta_code.dropna().unique().tolist()
                ta_dim = ta_dim[ta_dim.ta_code.isin(u_tas)]
                ro_master = ro_master[ro_master.ta_code.isin(u_tas)]
                ro_scope = ro_scope[ro_scope.ta_code.isin(u_tas)]

    filt_note = _filt_note(state)

    ctx = dict(
        cy_f=cy_f,
        ly_f=ly_f,
        scope=scope,
        b_cy=b_cy,
        b_ly=b_ly,
        branded=branded,
        branded_scope=branded_scope,
        monthly=monthly,
        ro_master=ro_master,
        ta_dim=ta_dim,
        ro_scope=ro_scope,
        product=state.product,
        cy=state.cy,
        ly=state.ly,
        months=list(state.months),
        period_lbl=state.period_lbl,
        fys=fys,
        multi_fy_mode=state.multi_fy_mode,
        cy_pairs=set(state.cy_pairs),
        ly_pairs=set(state.ly_pairs),
        TA_NAME=TA_NAME,
        districts=list(state.districts),
        rsa_labels=state.rsa_labels,
        coms=list(state.coms),
        hwy_nums=list(state.hwy_nums),
        filt_note=filt_note,
    )

    st.session_state["_pdo_ctx"] = ctx
    return ctx


def get_context() -> dict:
    """Return session-scoped context built by app.py on each rerun."""
    ctx = st.session_state.get("_pdo_ctx")
    if ctx is None:
        st.error("Dashboard context not initialized. Please reload the app.")
        st.stop()
    return ctx
