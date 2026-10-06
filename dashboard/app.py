"""Tableau de bord DVF : prix de l'immobilier par commune, lu dans les marts dbt.

Source : marts.mart_prix_commune_annee (agregats) et marts.fct_ventes (carte).
Palette categorielle validee (daltonisme) ; une commune garde sa couleur et sa forme tant qu'elle
est selectionnee.
"""
import math
import os

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Prix immobiliers - DVF", page_icon=None, layout="wide")

INK, MUTED, RULE, SURFACE = "#14232b", "#52514e", "#d6dddf", "#fcfcfb"
SLOTS = [("#2a78d6", "circle"), ("#eb6834", "square"), ("#1baf7a", "diamond"),
         ("#eda100", "triangle-up"), ("#e87ba4", "cross")]
MAX_COMMUNES = len(SLOTS)
DEPARTEMENTS = {"60": "Oise", "75": "Paris", "93": "Seine-Saint-Denis"}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap');
html, body, .stApp, .stApp *:not([data-testid="stIconMaterial"]):not(svg):not(path) {{ font-family: 'Public Sans', sans-serif; }}
.block-container {{ padding-top: 4.5rem; max-width: 1280px; }}
.page-title {{ font-size:1.05rem; font-weight:600; color:{INK}; margin:0 0 1rem 0; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
.kicker {{ color:{MUTED}; font-size:.92rem; margin:0 0 .2rem 0; }}
.headline {{ font-size:1.9rem; font-weight:700; line-height:1.2; color:{INK}; margin:0 0 .4rem 0; max-width:62rem; }}
.headline b {{ font-variant-numeric: tabular-nums; }}
.meta {{ color:{MUTED}; font-size:.85rem; }}
.panel-title {{ font-size:1.02rem; font-weight:600; color:{INK}; margin:0 0 .15rem 0; }}
.panel-sub {{ font-size:.85rem; color:{MUTED}; margin:0 0 .6rem 0; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background:{SURFACE}; border:1px solid {RULE};
    border-radius:6px; }}
.funnel td {{ padding:.28rem .9rem .28rem 0; font-variant-numeric: tabular-nums; }}
.funnel td:first-child {{ color:{MUTED}; }}
.legend-bar {{ height:10px; border-radius:2px; background:linear-gradient(90deg,#cfe1f7,#0b2f66); }}
.legend-labels {{ display:flex; justify-content:space-between; font-size:.8rem; color:{MUTED}; }}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def engine():
    e = os.environ
    url = (f"postgresql+psycopg2://{e.get('WH_USER', 'dvf')}:{e.get('WH_PASSWORD', 'dvf')}"
           f"@{e.get('WH_HOST', 'localhost')}:{e.get('WH_PORT', '5433')}/{e.get('WH_DB', 'dvf')}")
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def fmt(n, suffix="") -> str:
    return f"{n:,.0f}".replace(",", " ") + suffix


def lerp_color(t: float) -> list[int]:
    a, b = (207, 225, 247), (11, 47, 102)
    return [int(a[i] + (b[i] - a[i]) * t) for i in range(3)] + [190]


try:
    mart = query("select * from marts.mart_prix_commune_annee")
except Exception as exc:  # base absente ou pas encore alimentee
    st.error("Impossible de lire l'entrepot. Verifie que le pipeline a tourne : "
             "`docker compose ps`, puis lance le DAG `pipeline_dvf` dans Airflow.")
    st.caption(str(exc).splitlines()[0])
    st.stop()

if mart.empty:
    st.warning("Le mart est vide : lance le DAG `pipeline_dvf` dans Airflow.")
    st.stop()

mart["annee"] = mart["annee"].astype(int)
annees = sorted(mart["annee"].unique())
loaded_at = query("select max(_loaded_at) as t from raw.dvf")["t"].iloc[0]

# ---- filtres ---------------------------------------------------------------------------------
st.markdown("<p class='page-title'>Prix de l'immobilier par commune (Oise, Paris, Seine-Saint-Denis)</p>", unsafe_allow_html=True)
top = st.columns([1.3, 1, 1.4], gap="large")
with top[0]:
    type_local = st.segmented_control("Type de bien", ["Appartement", "Maison"],
                                      default="Appartement", key="type_local") or "Appartement"
with top[1]:
    annee = st.selectbox("Année", annees[::-1], index=0)
with top[2]:
    deps_dispo = sorted(mart["code_departement"].unique())
    deps = st.multiselect("Départements", deps_dispo, default=deps_dispo,
                          format_func=lambda d: f"{d} · {DEPARTEMENTS.get(d, d)}") or deps_dispo

sel = mart[(mart["type_local"] == type_local) & (mart["code_departement"].isin(deps))]
sel_year = sel[sel["annee"] == annee]

# communes comparees : par defaut les 3 plus actives
actives = (sel.groupby("nom_commune")["nb_ventes"].sum().sort_values(ascending=False))
defaut = [c for c in ["Compiègne", "Villetaneuse", "Paris 5e Arrondissement"] if c in actives.index]
if len(defaut) < 3:
    defaut = list(actives.index[:3])
communes = st.multiselect(f"Communes à comparer (maximum {MAX_COMMUNES})", list(actives.index),
                          default=defaut, max_selections=MAX_COMMUNES)

# une commune garde sa couleur tant qu'elle reste selectionnee
slots = st.session_state.setdefault("slots", {})
for c in list(slots):
    if c not in communes:
        del slots[c]
for c in communes:
    if c not in slots:
        used = set(slots.values())
        slots[c] = next(i for i in range(MAX_COMMUNES) if i not in used)

# ---- titre : la phrase qui resume la comparaison ---------------------------------------------
comp = sel_year[sel_year["nom_commune"].isin(communes)].sort_values("prix_m2_median")
if len(comp) >= 2:
    bas, haut = comp.iloc[0], comp.iloc[-1]
    ratio = haut["prix_m2_median"] / bas["prix_m2_median"]
    headline = (f"{haut['nom_commune']} : <b>{fmt(haut['prix_m2_median'])}&nbsp;€/m²</b>, "
                f"soit {ratio:.1f}&nbsp;fois {bas['nom_commune']} (<b>{fmt(bas['prix_m2_median'])}&nbsp;€/m²</b>)")
    kicker = f"Prix médian des {type_local.lower()}s vendus en {annee}"
else:
    headline = "Choisis au moins deux communes pour les comparer"
    kicker = f"Prix médian des {type_local.lower()}s"
fresh = f"Données chargées le {loaded_at:%d/%m/%Y}" if pd.notna(loaded_at) else ""
st.markdown(f"<p class='kicker'>{kicker}</p><p class='headline'>{headline}</p>"
            f"<p class='meta'>Source : DVF (data.gouv.fr), ventes de logements 2022-2025. {fresh}</p>",
            unsafe_allow_html=True)

# ---- evolution + classement ------------------------------------------------------------------
left, right = st.columns([1.35, 1], gap="large")

with left, st.container(border=True):
    st.markdown("<p class='panel-title'>Évolution du prix médian au m²</p>"
                "<p class='panel-sub'>Une ligne par commune, une valeur par année</p>",
                unsafe_allow_html=True)
    evo = sel[sel["nom_commune"].isin(communes)]
    if evo.empty:
        st.info("Aucune commune sélectionnée.")
    else:
        order = sorted(communes, key=lambda c: slots[c])
        colors = [SLOTS[slots[c]][0] for c in order]
        shapes = [SLOTS[slots[c]][1] for c in order]
        base = alt.Chart(evo).encode(
            x=alt.X("annee:O", title=None, axis=alt.Axis(labelAngle=0, labelColor=MUTED,
                                                         domainColor=RULE, tickColor=RULE)),
            y=alt.Y("prix_m2_median:Q", title="€/m² (médiane)", scale=alt.Scale(zero=False),
                    axis=alt.Axis(labelColor=MUTED, titleColor=MUTED, gridColor="#e6ebec",
                                  domain=False, format=",.0f")),
            color=alt.Color("nom_commune:N", scale=alt.Scale(domain=order, range=colors),
                            legend=alt.Legend(title=None, orient="top", labelColor=INK,
                                              labelFontSize=12, symbolType="stroke")),
            shape=alt.Shape("nom_commune:N", scale=alt.Scale(domain=order, range=shapes), legend=None),
            tooltip=[alt.Tooltip("nom_commune:N", title="Commune"), alt.Tooltip("annee:O", title="Année"),
                     alt.Tooltip("prix_m2_median:Q", title="Prix médian €/m²", format=",.0f"),
                     alt.Tooltip("nb_ventes:Q", title="Ventes")])
        chart = (base.mark_line(strokeWidth=2) + base.mark_point(size=70, filled=True, opacity=1,
                                                                  stroke=SURFACE, strokeWidth=2)
                 ).properties(height=330).configure_view(stroke=None).configure(background=SURFACE, font="Arial")
        st.altair_chart(chart, width="stretch")
        with st.expander("Voir les valeurs"):
            tab = evo.pivot_table(index="nom_commune", columns="annee", values="prix_m2_median")
            tab.index.name = "Commune"
            st.dataframe(tab.map(lambda v: fmt(v) if pd.notna(v) else "–"), width="stretch")

with right, st.container(border=True):
    ordre = st.segmented_control("Classement", ["Plus chères", "Moins chères"], default="Plus chères",
                                 label_visibility="collapsed") or "Plus chères"
    st.markdown(f"<p class='panel-title'>Communes les {'plus' if ordre == 'Plus chères' else 'moins'} chères en {annee}</p>"
                "<p class='panel-sub'>Prix médian au m², communes avec assez de ventes</p>",
                unsafe_allow_html=True)
    mini = st.slider("Ventes minimum par commune", 5, 500, 30, step=5)
    eligibles = sel_year[sel_year["nb_ventes"] >= mini]
    st.caption(f"{len(eligibles)} communes sur {len(sel_year)} ont au moins {mini} ventes ; les 12 premières sont affichées.")
    rank = (eligibles.sort_values("prix_m2_median", ascending=(ordre == "Moins chères"))
            .head(12).assign(nom_court=lambda d: d["nom_commune"].str.replace(" Arrondissement", "", regex=False)))
    if rank.empty:
        st.info("Aucune commune avec autant de ventes : baisse le minimum.")
    else:
        bars = alt.Chart(rank).mark_bar(cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
                                        color=SLOTS[0][0], size=14).encode(
            y=alt.Y("nom_court:N", sort=alt.EncodingSortField(field="prix_m2_median", order="ascending" if ordre == "Moins chères" else "descending"), title=None,
                    axis=alt.Axis(labelColor=INK, labelLimit=200, labelOverlap=False, domain=False, ticks=False)),
            x=alt.X("prix_m2_median:Q", title="€/m² (médiane)",
                    axis=alt.Axis(labelColor=MUTED, titleColor=MUTED, gridColor="#e6ebec",
                                  domain=False, format=",.0f")),
            tooltip=[alt.Tooltip("nom_commune:N", title="Commune"),
                     alt.Tooltip("prix_m2_median:Q", title="Prix médian €/m²", format=",.0f"),
                     alt.Tooltip("nb_ventes:Q", title="Ventes")])
        st.altair_chart(bars.properties(height=max(120, 26 * len(rank)))
                        .configure_view(stroke=None).configure(background=SURFACE, font="Arial", padding={"left": 48, "right": 8, "top": 4, "bottom": 4}), width="stretch")
        with st.expander("Voir les valeurs"):
            st.dataframe(rank[["nom_commune", "prix_m2_median", "nb_ventes"]]
                         .rename(columns={"nom_commune": "Commune", "prix_m2_median": "€/m² médian",
                                          "nb_ventes": "Ventes"}), hide_index=True, width="stretch")

# ---- carte -----------------------------------------------------------------------------------
with st.container(border=True):
    st.markdown(f"<p class='panel-title'>Chaque vente de {annee}</p>"
                "<p class='panel-sub'>Un point par vente ; plus c'est foncé, plus le prix au m² est élevé "
                "(échantillon de 6 000 ventes au plus)</p>", unsafe_allow_html=True)
    pts = query("""select longitude, latitude, prix_m2, surface_reelle_bati as surface, date_mutation
                   from marts.fct_ventes
                   where annee = :a and type_local = :t and code_departement = any(:d)
                     and longitude is not null and latitude is not null
                   order by random() limit 6000""", {"a": int(annee), "t": type_local, "d": list(deps)})
    if pts.empty:
        st.info("Aucune vente géolocalisée pour cette sélection.")
    else:
        lo, hi = pts["prix_m2"].quantile([0.05, 0.95])
        pts["color"] = pts["prix_m2"].map(lambda v: lerp_color(min(max((v - lo) / (hi - lo or 1), 0), 1)))
        pts["prix"] = pts["prix_m2"].map(lambda v: fmt(v, " €/m²"))
        pts["surf"] = pts["surface"].map(lambda v: fmt(v, " m²"))
        pts["date"] = pts["date_mutation"].astype(str)
        layer = pdk.Layer("ScatterplotLayer", pts, get_position=["longitude", "latitude"],
                          get_fill_color="color", get_radius=60, radius_min_pixels=2,
                          radius_max_pixels=7, pickable=True, stroked=False)
        lo0, lo1 = pts["longitude"].quantile([0.03, 0.97])
        la0, la1 = pts["latitude"].quantile([0.03, 0.97])
        zoom = min(math.log2(1050 / 512 * 360 / max(lo1 - lo0, 0.01) * 0.8),
                   math.log2(460 / 512 * 360 / max((la1 - la0) / math.cos(math.radians((la0 + la1) / 2)), 0.01) * 0.8))
        view = pdk.ViewState(longitude=float((lo0 + lo1) / 2), latitude=float((la0 + la1) / 2),
                             zoom=max(4.0, min(zoom, 13.0)))
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, map_style="light",
                                 tooltip={"html": "<b>{prix}</b><br/>{surf} · {date}"}),
                        height=460)
        c1, c2 = st.columns([1, 3])
        with c1:
            st.markdown(f"<div class='legend-bar'></div><div class='legend-labels'>"
                        f"<span>{fmt(lo)} €/m²</span><span>{fmt(hi)} €/m²</span></div>",
                        unsafe_allow_html=True)

# ---- d'ou viennent ces chiffres --------------------------------------------------------------
with st.expander("D'où viennent ces chiffres ?"):
    n = query("""select (select count(*) from raw.dvf) as brut,
                        (select count(*) from staging.stg_transactions) as propre,
                        (select count(*) from marts.fct_ventes) as ventes""").iloc[0]
    st.markdown(
        "<table class='funnel'>"
        f"<tr><td>Lignes brutes chargées</td><td><b>{fmt(n['brut'])}</b></td></tr>"
        f"<tr><td>Après suppression des doublons exacts</td><td><b>{fmt(n['propre'])}</b></td>"
        f"<td>{(1 - n['propre'] / n['brut']):.1%} écartées</td></tr>"
        f"<tr><td>Ventes de logements comparables</td><td><b>{fmt(n['ventes'])}</b></td></tr></table>",
        unsafe_allow_html=True)
    st.caption("Une vente est retenue si c'est une vente simple d'un seul logement, sans local commercial, "
               "avec une surface renseignée et un prix entre 300 et 40 000 €/m². Détail dans le README.")
