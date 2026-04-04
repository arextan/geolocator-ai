"""
app.py — Streamlit interface for GeoLocator AI.

Tabs:
  Live Analysis — upload an image, run the pipeline, see results + map
  History       — browse all rounds from geoguessr.db with overview map

Run:
    streamlit run app.py
"""

import tempfile
import time
from pathlib import Path

import duckdb
import folium
import pydeck as pdk
import polars as pl
import streamlit as st
from PIL import ImageGrab
from streamlit_folium import st_folium

st.set_page_config(
    page_title="GeoLocator AI",
    page_icon="🌍",
    layout="wide",
)

DB = "geoguessr.db"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(image_path: str) -> dict:
    from extractor import extract
    from router import route
    from geo import resolve

    features, raw = extract([image_path])
    router_result = route(features)
    geo_result = resolve(features, router_result)

    return {
        "p1":           features.get("pass_1", {}) or {},
        "p2":           features.get("pass_2", {}) or {},
        "lg":           features.get("location_guess", {}) or {},
        "router_result": router_result,
        "geo_result":   geo_result,
        "guess_lat":    geo_result["lat"],
        "guess_lng":    geo_result["lng"],
        "source":       geo_result["source"],
        "raw":          raw,
    }


# ---------------------------------------------------------------------------
# Map builders
# ---------------------------------------------------------------------------

def _score_color(score: float | None) -> list[int]:
    """Interpolate red→yellow→green based on score 0–5000."""
    if score is None:
        return [160, 160, 160, 180]
    t = max(0.0, min(1.0, score / 5000))
    if t < 0.5:
        r, g = 220, int(180 * t * 2)
    else:
        r, g = int(220 * (1 - (t - 0.5) * 2)), 180
    return [r, g, 40, 210]


def _live_map(
    guess_lat: float,
    guess_lng: float,
    actual_lat: float | None = None,
    actual_lng: float | None = None,
    height: int = 380,
) -> None:
    """Render a folium map with a blue guess marker and optional green actual marker + line."""
    if actual_lat is not None and actual_lng is not None:
        center_lat = (guess_lat + actual_lat) / 2
        center_lng = (guess_lng + actual_lng) / 2
    else:
        center_lat, center_lng = guess_lat, guess_lng

    m = folium.Map(location=[center_lat, center_lng], zoom_start=2, tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>')

    folium.Marker(
        location=[guess_lat, guess_lng],
        tooltip="Guess",
        icon=folium.Icon(color="blue", icon="crosshairs", prefix="fa"),
    ).add_to(m)

    if actual_lat is not None and actual_lng is not None:
        folium.Marker(
            location=[actual_lat, actual_lng],
            tooltip="Actual location",
            icon=folium.Icon(color="green", icon="map-marker", prefix="fa"),
        ).add_to(m)
        folium.PolyLine(
            locations=[[guess_lat, guess_lng], [actual_lat, actual_lng]],
            color="#e74c3c",
            weight=2.5,
            dash_array="6 4",
            tooltip="Distance line",
        ).add_to(m)

    st_folium(m, height=height, use_container_width=True, returned_objects=[])


def _overview_map(df: pl.DataFrame, height: int = 320) -> None:
    """Render a folium overview map with all guess locations colored by score."""
    map_df = df.filter(
        pl.col("guess_lat").is_not_null() & pl.col("guess_lng").is_not_null()
    ).select(["round_id", "guess_lat", "guess_lng", "guessed_country", "geoguessr_score"])

    m = folium.Map(location=[20, 0], zoom_start=2, tiles="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>')

    for row in map_df.iter_rows(named=True):
        r, g, b, _ = _score_color(row["geoguessr_score"])
        color_hex = f"#{r:02x}{g:02x}{b:02x}"
        score_val = row["geoguessr_score"]
        label = f"{row['round_id']} — {row['guessed_country'] or '?'} ({score_val or '?'} pts)"
        folium.CircleMarker(
            location=[row["guess_lat"], row["guess_lng"]],
            radius=5,
            color=color_hex,
            fill=True,
            fill_color=color_hex,
            fill_opacity=0.8,
            tooltip=label,
        ).add_to(m)

    st_folium(m, height=height, use_container_width=True, returned_objects=[])


# ---------------------------------------------------------------------------
# Score display
# ---------------------------------------------------------------------------

def _score_banner(pts: int, dist_km: float) -> None:
    if pts >= 4000:
        color, label = "#27ae60", "Excellent"
    elif pts >= 3000:
        color, label = "#f39c12", "Good"
    elif pts >= 1500:
        color, label = "#e67e22", "Average"
    else:
        color, label = "#e74c3c", "Poor"

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {color}18, {color}08);
            border: 1px solid {color}40;
            border-radius: 12px;
            padding: 1.2rem 1.5rem;
            text-align: center;
            margin: 0.5rem 0;
        ">
            <div style="font-size: 3.2rem; font-weight: 800; color: {color}; line-height: 1;">
                {pts:,}
            </div>
            <div style="font-size: 1rem; color: #666; margin-top: 0.1rem;">
                / 5,000 &nbsp;·&nbsp; {label}
            </div>
            <div style="font-size: 0.85rem; color: #999; margin-top: 0.4rem;">
                {dist_km:,.0f} km from actual location
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Feature table
# ---------------------------------------------------------------------------

def _feature_table(p1: dict, p2: dict) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.caption("Pass 1 — Deterministic")
        rows = [{"feature": k, "value": str(v) if v is not None else "—"} for k, v in p1.items()]
        st.dataframe(pl.DataFrame(rows), hide_index=True, use_container_width=True)
    with c2:
        st.caption("Pass 2 — Probabilistic")
        rows = [{"feature": k, "value": str(v) if v is not None else "—"} for k, v in p2.items()]
        st.dataframe(pl.DataFrame(rows), hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# Tab: Live Analysis
# ---------------------------------------------------------------------------

def _do_screenshot() -> str | None:
    """Show a 5-second countdown, capture the screen, save to a temp file.
    Returns the temp file path, or None on failure.
    """
    slot = st.empty()
    for i in range(5, 0, -1):
        slot.markdown(
            f"<div style='text-align:center;padding:2rem 0'>"
            f"<div style='font-size:5rem;font-weight:800;line-height:1'>{i}</div>"
            f"<div style='font-size:1rem;color:#888;margin-top:0.5rem'>"
            f"Switch to GeoGuessr now</div></div>",
            unsafe_allow_html=True,
        )
        time.sleep(1)
    slot.markdown(
        "<div style='text-align:center;padding:1rem 0;font-size:1.5rem'>📸 Capturing…</div>",
        unsafe_allow_html=True,
    )
    try:
        img = ImageGrab.grab()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            img.save(tmp.name, format="PNG")
            path = tmp.name
        slot.empty()
        return path
    except Exception as exc:
        slot.error(f"Screen capture failed: {exc}")
        return None


def tab_live() -> None:
    # ------------------------------------------------------------------
    # Input row: file uploader on the left, screenshot button on the right
    # ------------------------------------------------------------------
    up_col, btn_col = st.columns([3, 1], gap="medium")

    with up_col:
        uploaded = st.file_uploader(
            "Upload a Street View image",
            type=["png", "jpg", "jpeg", "webp"],
            label_visibility="collapsed",
        )

    with btn_col:
        st.markdown("<div style='height:0.3rem'></div>", unsafe_allow_html=True)
        take_screenshot = st.button(
            "📸  Screenshot in 5s",
            use_container_width=True,
            help="Click, switch to GeoGuessr, then hold still — the screen is captured after 5 seconds.",
        )

    # ------------------------------------------------------------------
    # Resolve image path from either source
    # ------------------------------------------------------------------
    tmp_path: str | None = None

    if take_screenshot:
        tmp_path = _do_screenshot()
        if tmp_path:
            st.session_state["screenshot_path"] = tmp_path
        else:
            return
    elif uploaded is not None:
        suffix = Path(uploaded.name).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name
        st.session_state["screenshot_path"] = tmp_path
    elif "screenshot_path" in st.session_state:
        # Re-use the last screenshot when the user adjusts actual-location
        # inputs (which trigger a rerun without a new upload/screenshot)
        tmp_path = st.session_state["screenshot_path"]

    if tmp_path is None:
        st.markdown(
            "<div style='border:2px dashed #ddd;border-radius:12px;"
            "padding:3rem;text-align:center;color:#aaa'>"
            "<div style='font-size:2.5rem'>🌍</div>"
            "<div style='margin-top:0.5rem'>Upload an image or use the Screenshot button</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    with st.spinner("Running pipeline…"):
        try:
            result = _run_pipeline(tmp_path)
        except Exception as exc:
            st.error(f"Pipeline error: {exc}")
            return

    lg        = result["lg"]
    geo_result = result["geo_result"]
    guess_lat  = result["guess_lat"]
    guess_lng  = result["guess_lng"]
    p1, p2     = result["p1"], result["p2"]

    city    = lg.get("city")    or "Unknown"
    country = lg.get("country") or "Unknown"
    conf    = lg.get("confidence") or 0.0
    reason  = lg.get("reasoning") or "—"
    source  = geo_result.get("source", "—")

    # ------------------------------------------------------------------
    # Two-column layout: image | results + map
    # ------------------------------------------------------------------
    left, right = st.columns([1, 1.4], gap="large")

    with left:
        st.image(tmp_path, use_container_width=True)

        # Actual location inputs live under the image
        st.markdown("**Actual location** *(optional)*")
        a1, a2 = st.columns(2)
        actual_lat_val = a1.number_input("Latitude",  value=0.0, format="%.5f", key="alat",
                                          label_visibility="visible")
        actual_lng_val = a2.number_input("Longitude", value=0.0, format="%.5f", key="alng",
                                          label_visibility="visible")
        has_actual = st.checkbox("Score against actual", value=False, key="has_actual")

    with right:
        # Location heading
        st.markdown(
            f"<div style='font-size:1.7rem;font-weight:700;margin-bottom:0.1rem'>"
            f"{city}, {country}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Source: **{source}** &nbsp;·&nbsp; {guess_lat:.4f}, {guess_lng:.4f}")

        mc1, mc2 = st.columns(2)
        mc1.metric("Confidence", f"{conf:.0%}")
        mc2.metric("Coord source", source)

        st.markdown(f"*{reason}*")
        st.markdown("")

        # Score banner (if actual provided)
        actual_lat = actual_lng = None
        if has_actual and (actual_lat_val != 0.0 or actual_lng_val != 0.0):
            from scoring import haversine, geoguessr_score
            actual_lat = actual_lat_val
            actual_lng = actual_lng_val
            dist_km = haversine(guess_lat, guess_lng, actual_lat, actual_lng)
            pts = geoguessr_score(dist_km)
            _score_banner(pts, dist_km)

        # Map — full width of right column
        _live_map(guess_lat, guess_lng, actual_lat, actual_lng, height=380)

    # ------------------------------------------------------------------
    # Feature expander — full width below
    # ------------------------------------------------------------------
    with st.expander("Extracted features"):
        _feature_table(p1, p2)

    with st.expander("Raw Claude response"):
        st.code(result.get("raw") or "(empty)", language="json")


# ---------------------------------------------------------------------------
# History helpers
# ---------------------------------------------------------------------------

def _load_history() -> pl.DataFrame:
    try:
        con = duckdb.connect(DB, read_only=True)
        df = pl.from_arrow(con.execute("""
            SELECT
                round_id, guessed_city, guessed_country,
                guess_confidence, path_taken, distance_km, geoguessr_score,
                guess_reasoning, guess_lat, guess_lng, actual_lat, actual_lng,
                script, language, language_confidence, driving_side,
                biome, terrain, architecture, road_markings, road_surface,
                infrastructure_quality, vegetation_specific, soil_color,
                pole_type, plate_format, place_name, raw_response
            FROM rounds
            ORDER BY timestamp DESC
        """).arrow())
        con.close()
        return df
    except Exception as exc:
        st.warning(f"Could not load history: {exc}")
        return pl.DataFrame()


# ---------------------------------------------------------------------------
# Tab: History
# ---------------------------------------------------------------------------

def tab_history() -> None:
    df = _load_history()
    if df.is_empty():
        st.info("No rounds in geoguessr.db. Run main.py first.")
        return

    scored_df = df.filter(pl.col("geoguessr_score").is_not_null())
    total     = len(df)
    scored    = len(scored_df)

    # Summary metrics
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total rounds",  total)
    m2.metric("Scored",        scored)
    m3.metric("Avg score",     f"{scored_df['geoguessr_score'].mean():,.0f}" if scored else "—")
    m4.metric("Median score",  f"{scored_df['geoguessr_score'].median():,.0f}" if scored else "—")
    m5.metric(">4000 pts",     scored_df.filter(pl.col("geoguessr_score") >= 4000).height if scored else 0)

    # Overview map — all guesses colored by score
    st.subheader("All guess locations")
    st.caption("Green = high score · Red = low score · Grey = unscored")
    _overview_map(df, height=320)

    st.divider()

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------
    fc1, fc2, fc3 = st.columns(3)
    conf_min, conf_max = fc1.select_slider(
        "Confidence",
        options=[0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        value=(0.0, 1.0),
    )
    score_min, score_max = fc2.select_slider(
        "Score range",
        options=[0, 500, 1000, 2000, 3000, 4000, 5000],
        value=(0, 5000),
    )
    country_filter = fc3.text_input("Country filter", placeholder="e.g. Brazil", value="")

    filtered = df
    filtered = filtered.filter(
        pl.col("guess_confidence").is_null() |
        pl.col("guess_confidence").is_between(conf_min, conf_max)
    )
    filtered = filtered.filter(
        pl.col("geoguessr_score").is_null() |
        pl.col("geoguessr_score").is_between(score_min, score_max)
    )
    if country_filter.strip():
        filtered = filtered.filter(
            pl.col("guessed_country").str.to_lowercase().str.contains(
                country_filter.strip().lower()
            )
        )

    st.caption(f"Showing {len(filtered):,} of {total:,} rounds")

    # ------------------------------------------------------------------
    # Table
    # ------------------------------------------------------------------
    TABLE_COLS = [
        "round_id", "guessed_city", "guessed_country",
        "guess_confidence", "path_taken", "distance_km", "geoguessr_score",
    ]
    event = st.dataframe(
        filtered.select(TABLE_COLS),
        hide_index=True,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "round_id":         st.column_config.TextColumn("Round"),
            "guessed_city":     st.column_config.TextColumn("City"),
            "guessed_country":  st.column_config.TextColumn("Country"),
            "guess_confidence": st.column_config.NumberColumn("Conf", format="%.2f"),
            "path_taken":       st.column_config.TextColumn("Path"),
            "distance_km":      st.column_config.NumberColumn("km", format="%.0f"),
            "geoguessr_score":  st.column_config.NumberColumn("Score"),
        },
    )

    # ------------------------------------------------------------------
    # Row detail
    # ------------------------------------------------------------------
    selected_rows = (
        event.selection.get("rows", []) if hasattr(event, "selection") else []
    )

    chosen_id: str | None = None
    if selected_rows:
        chosen_id = filtered.select(TABLE_COLS)["round_id"][selected_rows[0]]

    if not chosen_id:
        st.caption("Click a row to see full detail.")
        return

    row = filtered.filter(pl.col("round_id") == chosen_id).row(0, named=True)

    st.divider()

    det_left, det_right = st.columns([1, 1.4], gap="large")

    with det_left:
        st.subheader(chosen_id)

        d1, d2 = st.columns(2)
        d1.metric("Guessed",    f"{row['guessed_city'] or '?'}, {row['guessed_country'] or '?'}")
        d2.metric("Confidence", f"{row['guess_confidence']:.0%}" if row["guess_confidence"] else "—")

        if row["geoguessr_score"] is not None:
            _score_banner(row["geoguessr_score"], row["distance_km"] or 0)

        if row["guess_reasoning"]:
            st.markdown(f"*{row['guess_reasoning']}*")

        FEATURE_KEYS = [
            "script", "language", "language_confidence", "driving_side",
            "biome", "terrain", "architecture", "road_markings", "road_surface",
            "infrastructure_quality", "vegetation_specific", "soil_color",
            "pole_type", "plate_format", "place_name",
        ]
        with st.expander("Feature trace"):
            feat_rows = [
                {"feature": k, "value": str(row.get(k)) if row.get(k) is not None else "—"}
                for k in FEATURE_KEYS
            ]
            st.dataframe(pl.DataFrame(feat_rows), hide_index=True, use_container_width=True)

        with st.expander("Raw Claude response"):
            st.code(row.get("raw_response") or "(empty)", language="json")

    with det_right:
        if row.get("guess_lat") and row.get("guess_lng"):
            _live_map(
                row["guess_lat"], row["guess_lng"],
                row.get("actual_lat"), row.get("actual_lng"),
                height=440,
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

st.markdown(
    "<h1 style='margin-bottom:0.1rem'>🌍 GeoLocator AI</h1>"
    "<p style='color:#888;margin-top:0;margin-bottom:1.2rem'>"
    "Street View geolocation powered by Claude Sonnet</p>",
    unsafe_allow_html=True,
)

tab1, tab2 = st.tabs(["🔍  Live Analysis", "📊  History"])

with tab1:
    tab_live()

with tab2:
    tab_history()
