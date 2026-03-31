"""
analyze.py — Post-run analysis of geoguessr.db.

Outputs to terminal:
  1. Score distribution
  2. Feature null rates (present vs null avg score)
  3. Country confusion analysis
  4. Score by text detection
  5. Confidence calibration
  6. Top 30 worst rounds
  7. Systematic failure patterns
  8. Score by guessed country

Saves to docs/:
  score_distribution.png
  confidence_calibration.png
  worst_rounds.csv

Usage:
    python analyze.py
    python analyze.py --db geoguessr.db
"""

import argparse
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import duckdb
import polars as pl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="darkgrid")

DOCS = Path("docs")
DOCS.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Offline coordinate → country via bounding boxes (no API, no external data)
# Entries are ordered most-specific first to handle geographic overlaps.
# ---------------------------------------------------------------------------
_COUNTRY_BOXES = [
    # (name, continent, lat_min, lat_max, lng_min, lng_max)
    # Oceania
    ("New Zealand",    "Oceania",        -47.3, -34.4,  166.4, 178.6),
    ("Australia",      "Oceania",        -43.7, -10.7,  113.2, 153.7),
    # Africa
    ("South Africa",   "Africa",         -35.0, -22.1,   16.5,  33.0),
    ("Botswana",       "Africa",         -26.9, -18.0,   20.0,  29.4),
    ("Zimbabwe",       "Africa",         -22.4, -15.6,   25.2,  33.1),
    ("Mozambique",     "Africa",         -26.9, -10.5,   32.3,  40.9),
    ("Zambia",         "Africa",         -18.1,  -8.2,   22.0,  33.7),
    ("Tanzania",       "Africa",         -11.7,  -1.0,   29.3,  40.4),
    ("Kenya",          "Africa",          -4.7,   5.0,   34.0,  42.0),
    ("Uganda",         "Africa",          -1.5,   4.2,   29.6,  35.0),
    ("Ethiopia",       "Africa",           3.4,  15.0,   33.0,  48.0),
    ("Nigeria",        "Africa",           4.3,  14.0,    2.7,  15.0),
    ("Ghana",          "Africa",           4.7,  11.2,   -3.3,   1.2),
    ("Senegal",        "Africa",          12.3,  16.7,  -17.6, -11.4),
    ("Morocco",        "Africa",          27.7,  35.9,  -13.2,  -1.0),
    ("Tunisia",        "Africa",          30.2,  37.5,    7.5,  11.6),
    ("Egypt",          "Africa",          22.0,  31.7,   24.7,  37.1),
    # South America
    ("Chile",          "South America",  -55.9, -17.5,  -75.7, -66.4),
    ("Argentina",      "South America",  -55.0, -21.8,  -73.6, -53.5),
    ("Bolivia",        "South America",  -22.9,  -9.7,  -69.6, -57.5),
    ("Peru",           "South America",  -18.4,  -0.1,  -81.4, -68.5),
    ("Brazil",         "South America",  -33.8,   5.3,  -73.5, -34.5),
    ("Colombia",       "South America",   -4.2,  12.5,  -79.0, -66.9),
    ("Ecuador",        "South America",   -5.0,   1.5,  -80.8, -75.2),
    ("Venezuela",      "South America",    0.6,  12.2,  -73.4, -59.8),
    ("Uruguay",        "South America",  -34.9, -30.1,  -58.5, -53.2),
    ("Paraguay",       "South America",  -27.6, -19.3,  -62.7, -54.3),
    # North America
    ("Mexico",         "North America",   14.5,  32.7, -118.0, -86.5),
    ("Canada",         "North America",   41.6,  83.1, -141.0, -52.0),
    ("United States",  "North America",   24.0,  49.5, -125.0, -66.0),
    # Europe
    ("Portugal",       "Europe",          36.8,  42.2,   -9.5,  -6.2),
    ("Spain",          "Europe",          35.9,  43.8,   -9.4,   4.4),
    ("United Kingdom", "Europe",          49.9,  60.9,   -8.2,   2.0),
    ("Ireland",        "Europe",          51.3,  55.4,  -10.5,  -5.9),
    ("France",         "Europe",          41.3,  51.1,   -5.3,   9.6),
    ("Belgium",        "Europe",          49.5,  51.5,    2.5,   6.4),
    ("Netherlands",    "Europe",          50.8,  53.6,    3.3,   7.2),
    ("Germany",        "Europe",          47.3,  55.1,    5.9,  15.0),
    ("Switzerland",    "Europe",          45.8,  47.8,    5.9,  10.5),
    ("Austria",        "Europe",          46.4,  49.0,    9.5,  17.2),
    ("Italy",          "Europe",          36.6,  47.1,    6.6,  18.5),
    ("Greece",         "Europe",          34.8,  42.0,   19.4,  28.3),
    ("Denmark",        "Europe",          54.6,  57.8,    8.1,  15.2),
    ("Sweden",         "Europe",          55.3,  69.1,   10.9,  24.2),
    ("Norway",         "Europe",          57.8,  71.2,    4.5,  31.2),
    ("Finland",        "Europe",          59.8,  70.1,   20.0,  31.6),
    ("Poland",         "Europe",          49.0,  54.9,   14.1,  24.2),
    ("Czech Republic", "Europe",          48.5,  51.1,   12.1,  18.9),
    ("Hungary",        "Europe",          45.7,  48.6,   16.1,  22.9),
    ("Romania",        "Europe",          43.6,  48.3,   20.3,  30.0),
    ("Bulgaria",       "Europe",          41.2,  44.2,   22.4,  28.6),
    ("Ukraine",        "Europe",          44.4,  52.4,   22.1,  40.2),
    ("Turkey",         "Europe/Asia",     35.8,  42.1,   25.7,  44.8),
    ("Russia",         "Europe/Asia",     41.2,  82.0,   19.9, 180.0),
    # Middle East
    ("Israel",         "Middle East",     29.5,  33.3,   34.3,  35.9),
    ("Jordan",         "Middle East",     29.2,  33.4,   34.9,  39.3),
    ("UAE",            "Middle East",     22.6,  26.1,   51.6,  56.4),
    ("Saudi Arabia",   "Middle East",     16.4,  32.2,   34.6,  55.7),
    # Asia
    ("Sri Lanka",      "Asia",             5.9,   9.8,   79.7,  81.9),
    ("Bangladesh",     "Asia",            20.7,  26.6,   88.0,  92.7),
    ("India",          "Asia",             6.7,  35.7,   68.1,  97.4),
    ("Singapore",      "Asia",             1.1,   1.5,  103.6, 104.1),
    ("Malaysia",       "Asia",             0.9,   7.4,   99.6, 119.3),
    ("Vietnam",        "Asia",             8.4,  23.4,  102.1, 109.5),
    ("Thailand",       "Asia",             5.6,  20.5,   97.3, 105.7),
    ("Philippines",    "Asia",             4.6,  21.1,  116.9, 126.7),
    ("Taiwan",         "Asia",            21.9,  25.3,  120.0, 122.0),
    ("South Korea",    "Asia",            33.1,  38.6,  124.6, 130.0),
    ("Japan",          "Asia",            24.2,  45.7,  122.9, 153.0),
    ("China",          "Asia",            18.2,  53.6,   73.5, 135.1),
    ("Mongolia",       "Asia",            41.6,  52.1,   87.8, 119.9),
    ("Kazakhstan",     "Asia",            40.6,  55.4,   50.3,  87.4),
    ("Indonesia",      "Asia",           -11.0,   6.1,   95.0, 141.0),
]


def _coord_to_country(lat: float | None, lng: float | None) -> tuple[str, str]:
    """Return (country, continent). Falls back to broad continental label."""
    if lat is None or lng is None:
        return "Unknown", "Unknown"
    for name, continent, lat_min, lat_max, lng_min, lng_max in _COUNTRY_BOXES:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return name, continent
    # Broad continental fallbacks for unmatched coords
    if -35 <= lat <= 37 and -20 <= lng <= 52:
        return "Africa (other)", "Africa"
    if -56 <= lat <= 13 and -82 <= lng <= -34:
        return "South America (other)", "South America"
    if 14 <= lat <= 73 and -170 <= lng <= -52:
        return "North America (other)", "North America"
    if 35 <= lat <= 72 and -12 <= lng <= 45:
        return "Europe (other)", "Europe"
    if -10 <= lat <= 55 and 45 <= lng <= 150:
        return "Asia (other)", "Asia"
    if -47 <= lat <= -10 and 110 <= lng <= 180:
        return "Oceania (other)", "Oceania"
    return "Unknown", "Unknown"


SEP = "=" * 64

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="Analyze geoguessr.db results")
parser.add_argument("--db", default="geoguessr.db")
args = parser.parse_args()

con = duckdb.connect(args.db, read_only=True)
df_all = pl.from_arrow(con.execute("SELECT * FROM rounds").arrow())
con.close()

df = df_all.filter(pl.col("geoguessr_score").is_not_null())
total = len(df_all)
scored = len(df)
print(f"Loaded {total} rounds ({scored} with scores)\n")

# Attach actual country/continent via bounding-box lookup
actual_countries, actual_continents = [], []
for row in df.select(["actual_lat", "actual_lng"]).iter_rows(named=True):
    c, cont = _coord_to_country(row["actual_lat"], row["actual_lng"])
    actual_countries.append(c)
    actual_continents.append(cont)

df = df.with_columns([
    pl.Series("actual_country",   actual_countries),
    pl.Series("actual_continent", actual_continents),
])

# ---------------------------------------------------------------------------
# 1. Score distribution
# ---------------------------------------------------------------------------
print(SEP)
print("1. SCORE DISTRIBUTION")
print(SEP)

scores = df["geoguessr_score"].to_list()
print(f"  mean:   {df['geoguessr_score'].mean():.0f}")
print(f"  median: {df['geoguessr_score'].median():.0f}")
print(f"  std:    {df['geoguessr_score'].std():.0f}")
print(f"  min:    {df['geoguessr_score'].min()}")
print(f"  max:    {df['geoguessr_score'].max()}")
print()
for lo, hi in [(0,500),(500,1000),(1000,2000),(2000,3000),(3000,4000),(4000,5000)]:
    n = df.filter((pl.col("geoguessr_score") >= lo) & (pl.col("geoguessr_score") < hi)).height
    bar = "#" * (n // 5)
    print(f"  {lo:>5}–{hi}: {n:>4}  {bar}")

fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(scores, bins=50, color="steelblue", edgecolor="white", linewidth=0.4)
ax.axvline(df["geoguessr_score"].mean(),   color="tomato", linestyle="--",
           label=f"mean={df['geoguessr_score'].mean():.0f}")
ax.axvline(df["geoguessr_score"].median(), color="orange", linestyle="--",
           label=f"median={df['geoguessr_score'].median():.0f}")
ax.set_xlabel("GeoGuessr Score")
ax.set_ylabel("Rounds")
ax.set_title(f"Score Distribution — V2 Direct Claude Inference (n={scored})")
ax.legend()
plt.tight_layout()
plt.savefig(DOCS / "score_distribution.png", dpi=150)
plt.close()
print(f"\n  → docs/score_distribution.png")

# ---------------------------------------------------------------------------
# 2. Feature null rates
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("2. FEATURE NULL RATES  (null% | n present | avg score: present vs null)")
print(SEP)

SCALAR_FEATURES = [
    "language", "script", "driving_side", "biome", "terrain",
    "architecture", "road_markings", "road_surface", "infrastructure_quality",
    "plate_format", "pole_type", "soil_color", "vegetation_specific",
    "sky_condition", "place_name", "route_number", "domain_extension",
    "currency_symbol",
]

print(f"\n  {'feature':<28} {'null%':>5}  {'n_present':>9}  {'avg_present':>11}  {'avg_null':>8}")
print(f"  {'-'*28}  {'-'*5}  {'-'*9}  {'-'*11}  {'-'*8}")

for feat in SCALAR_FEATURES:
    if feat not in df.columns:
        continue
    present = df.filter(pl.col(feat).is_not_null())
    absent  = df.filter(pl.col(feat).is_null())
    null_pct = 100.0 * absent.height / scored
    avg_p = f"{present['geoguessr_score'].mean():.0f}" if present.height else "—"
    avg_n = f"{absent['geoguessr_score'].mean():.0f}"  if absent.height  else "—"
    print(f"  {feat:<28} {null_pct:>4.0f}%  {present.height:>9}  {avg_p:>11}  {avg_n:>8}")

# readable_text is a list column
has_text = df.filter(
    pl.col("readable_text").is_not_null() & (pl.col("readable_text").list.len() > 0)
)
no_text = df.filter(
    pl.col("readable_text").is_null() | (pl.col("readable_text").list.len() == 0)
)
null_pct = 100.0 * no_text.height / scored
avg_p = f"{has_text['geoguessr_score'].mean():.0f}" if has_text.height else "—"
avg_n = f"{no_text['geoguessr_score'].mean():.0f}"  if no_text.height  else "—"
print(f"  {'readable_text':<28} {null_pct:>4.0f}%  {has_text.height:>9}  {avg_p:>11}  {avg_n:>8}")

# ---------------------------------------------------------------------------
# 3. Country confusion analysis
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("3. COUNTRY CONFUSION ANALYSIS")
print(SEP)

known = df.filter(pl.col("actual_country") != "Unknown")
print(f"  {known.height}/{scored} rounds with identified actual country\n")

actual_summary = (
    known.group_by("actual_country")
    .agg(pl.len().alias("n"), pl.col("geoguessr_score").mean().alias("avg"))
    .sort("n", descending=True)
    .filter(pl.col("n") >= 3)
)

print(f"  {'actual country':<28} {'n':>4}  {'avg':>6}  top guessed countries")
print(f"  {'-'*28}  {'-'*4}  {'-'*6}  {'-'*38}")
for ac_row in actual_summary.iter_rows(named=True):
    ac = ac_row["actual_country"]
    sub = known.filter(pl.col("actual_country") == ac)
    top_g = (
        sub.filter(pl.col("guessed_country").is_not_null())
        .group_by("guessed_country")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .head(3)
    )
    guesses = ", ".join(
        f"{r['guessed_country']}({r['n']})" for r in top_g.iter_rows(named=True)
    )
    print(f"  {ac:<28} {ac_row['n']:>4}  {ac_row['avg']:>6.0f}  {guesses}")

print(f"\n  Cross-continent misidentification patterns:")
cross = [
    ("Africa",        ["United States", "Mexico", "Brazil", "Colombia", "Australia"]),
    ("Oceania",       ["United States", "Brazil", "South Africa", "Mexico"]),
    ("South America", ["United States", "Mexico", "Spain", "Portugal"]),
    ("Asia",          ["United States", "Australia", "Brazil"]),
    ("North America", ["Brazil", "Australia", "South Africa"]),
]
for actual_cont, wrong_list in cross:
    sub = known.filter(
        (pl.col("actual_continent") == actual_cont) &
        pl.col("guessed_country").is_in(wrong_list)
    )
    if sub.height == 0:
        continue
    print(f"\n  Actual={actual_cont} → wrong continent ({sub.height} rounds):")
    for wc in wrong_list:
        wc_sub = sub.filter(pl.col("guessed_country") == wc)
        if wc_sub.height > 0:
            avg = wc_sub["geoguessr_score"].mean()
            print(f"    guessed {wc:<28} {wc_sub.height:>3}×, avg {avg:.0f} pts")

# ---------------------------------------------------------------------------
# 4. Score by text detection
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("4. SCORE BY TEXT DETECTION")
print(SEP)

print(f"  With readable_text:    {has_text.height:>4} rounds, avg {has_text['geoguessr_score'].mean():.0f} pts")
print(f"  Without readable_text: {no_text.height:>4} rounds, avg {no_text['geoguessr_score'].mean():.0f} pts")

for label, feat in [("Language identified", "language"), ("Place name found", "place_name")]:
    yes = df.filter(pl.col(feat).is_not_null())
    no  = df.filter(pl.col(feat).is_null())
    print(f"\n  {label}:    {yes.height:>4} rounds, avg {yes['geoguessr_score'].mean():.0f} pts")
    print(f"  {'No ' + label.lower()}:    {no.height:>4} rounds, avg {no['geoguessr_score'].mean():.0f} pts")

# ---------------------------------------------------------------------------
# 5. Confidence calibration
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("5. CONFIDENCE CALIBRATION  (is Claude's confidence predictive?)")
print(SEP)

cal = df.filter(pl.col("guess_confidence").is_not_null())
bin_edges  = [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
bin_labels = ["0.0-0.2","0.2-0.3","0.3-0.4","0.4-0.5","0.5-0.6","0.6-0.7","0.7-0.8","0.8-0.9","0.9-1.0"]

print(f"\n  {'bin':<10} {'n':>4}  {'avg_score':>10}  {'median':>8}")
print(f"  {'-'*10}  {'-'*4}  {'-'*10}  {'-'*8}")

plot_x, plot_y, plot_n = [], [], []
for i, label in enumerate(bin_labels):
    lo, hi = bin_edges[i], bin_edges[i + 1]
    sub = cal.filter((pl.col("guess_confidence") >= lo) & (pl.col("guess_confidence") < hi))
    if sub.height == 0:
        continue
    avg = sub["geoguessr_score"].mean()
    med = sub["geoguessr_score"].median()
    print(f"  {label:<10} {sub.height:>4}  {avg:>10.0f}  {med:>8.0f}")
    plot_x.append((lo + hi) / 2)
    plot_y.append(avg)
    plot_n.append(sub.height)

fig, ax1 = plt.subplots(figsize=(9, 5))
ax1.plot(plot_x, plot_y, "o-", color="steelblue", linewidth=2, markersize=8, label="avg score")
ax1.axhline(df["geoguessr_score"].mean(), color="gray", linestyle="--",
            alpha=0.5, label=f"overall avg ({df['geoguessr_score'].mean():.0f})")
ax1.set_xlabel("Claude guess_confidence")
ax1.set_ylabel("Avg GeoGuessr Score", color="steelblue")
ax1.set_title("Confidence Calibration — Is Claude's Confidence Predictive?")
ax1.set_xlim(0, 1)
ax1.set_ylim(0, 5000)
ax2 = ax1.twinx()
ax2.bar(plot_x, plot_n, width=0.07, alpha=0.2, color="steelblue", label="n rounds")
ax2.set_ylabel("Rounds per bin", color="gray")
h1, l1 = ax1.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax1.legend(h1 + h2, l1 + l2, loc="upper left")
plt.tight_layout()
plt.savefig(DOCS / "confidence_calibration.png", dpi=150)
plt.close()
print(f"\n  → docs/confidence_calibration.png")

# ---------------------------------------------------------------------------
# 6. Top 30 worst rounds
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("6. TOP 30 WORST ROUNDS")
print(SEP)

worst = (
    df.sort("geoguessr_score")
    .head(30)
    .select([
        "round_id", "guessed_city", "guessed_country",
        "actual_lat", "actual_lng", "actual_country",
        "distance_km", "guess_confidence", "guess_reasoning", "geoguessr_score",
    ])
)

print(f"\n  {'round_id':<12}  {'guessed':<36}  {'actual':<22}  {'km':>6}  {'pts':>4}  {'conf':>5}")
print(f"  {'-'*12}  {'-'*36}  {'-'*22}  {'-'*6}  {'-'*4}  {'-'*5}")
for row in worst.iter_rows(named=True):
    guessed = f"{row['guessed_city'] or '?'}, {row['guessed_country'] or '?'}"
    conf    = row["guess_confidence"] or 0.0
    print(
        f"  {row['round_id']:<12}  {guessed:<36}  {row['actual_country']:<22}"
        f"  {row['distance_km']:>6.0f}  {row['geoguessr_score']:>4}  {conf:>5.2f}"
    )
    if row["guess_reasoning"]:
        print(f"    reasoning: {row['guess_reasoning']}")

worst.write_csv(DOCS / "worst_rounds.csv")
print(f"\n  → docs/worst_rounds.csv")

# ---------------------------------------------------------------------------
# 7. Systematic failure patterns
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("7. SYSTEMATIC FAILURE PATTERNS")
print(SEP)

# Wrong continent
wrong_cont = df.filter(pl.col("distance_km") > 10_000)
print(f"\n  Wrong continent (>10,000 km): {wrong_cont.height} rounds "
      f"({100*wrong_cont.height/scored:.1f}%)")
if wrong_cont.height > 0:
    top_wc = (
        wrong_cont.filter(pl.col("guessed_country").is_not_null())
        .group_by("guessed_country")
        .agg(pl.len().alias("n"))
        .sort("n", descending=True)
        .head(8)
    )
    for row in top_wc.iter_rows(named=True):
        print(f"    guessed {row['guessed_country']:<30} {row['n']:>3}×")

# Southern Africa → Americas
sa_wrong = df.filter(
    pl.col("actual_lat").is_not_null() &
    pl.col("actual_lat").is_between(-35, -15) &
    pl.col("actual_lng").is_between(15, 40) &
    pl.col("guessed_country").is_in([
        "United States", "Mexico", "Brazil", "Colombia", "Argentina", "Chile",
    ])
)
print(f"\n  Southern Africa guessed as Americas: {sa_wrong.height} rounds")
for row in sa_wrong.select(
    ["round_id", "guessed_city", "guessed_country", "distance_km", "geoguessr_score"]
).iter_rows(named=True):
    print(f"    {row['round_id']}: {row['guessed_city']}, {row['guessed_country']}"
          f" — {row['distance_km']:.0f} km, {row['geoguessr_score']} pts")

# Per-country accuracy for the four most-represented actual countries
for bbox_country, (lat_lo, lat_hi, lng_lo, lng_hi) in [
    ("Australia",     (-43.7, -10.7,  113.2, 153.7)),
    ("Brazil",        (-33.8,   5.3,  -73.5, -34.5)),
    ("United States", ( 24.0,  49.5, -125.0, -66.0)),
    ("South Africa",  (-35.0, -22.1,   16.5,  33.0)),
]:
    actual = df.filter(
        pl.col("actual_lat").is_not_null() &
        pl.col("actual_lat").is_between(lat_lo, lat_hi) &
        pl.col("actual_lng").is_between(lng_lo, lng_hi)
    )
    wrong = actual.filter(pl.col("guessed_country") != bbox_country)
    if actual.height == 0:
        continue
    pct = 100 * wrong.height / actual.height
    print(f"\n  {bbox_country} ({actual.height} rounds): "
          f"{wrong.height} guessed wrong ({pct:.0f}%)")
    if wrong.height > 0:
        top = (
            wrong.group_by("guessed_country")
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
            .head(5)
        )
        for row in top.iter_rows(named=True):
            print(f"    → guessed {row['guessed_country']}: {row['n']}×")

# High confidence but badly wrong
hc_wrong = df.filter(
    (pl.col("guess_confidence") >= 0.7) & (pl.col("distance_km") > 5_000)
)
print(f"\n  High confidence (≥0.7) but >5,000 km off: {hc_wrong.height} rounds")
for row in hc_wrong.sort("distance_km", descending=True).head(10).iter_rows(named=True):
    print(f"    {row['round_id']}: conf={row['guess_confidence']:.2f}  "
          f"guessed {row['guessed_city']},{row['guessed_country']}  "
          f"actual={row['actual_country']}  "
          f"{row['distance_km']:.0f} km  {row['geoguessr_score']} pts")

# ---------------------------------------------------------------------------
# 8. Score by guessed country
# ---------------------------------------------------------------------------
print(f"\n{SEP}")
print("8. SCORE BY GUESSED COUNTRY  (min 5 rounds)")
print(SEP)

by_country = (
    df.filter(pl.col("guessed_country").is_not_null())
    .group_by("guessed_country")
    .agg(
        pl.len().alias("n"),
        pl.col("geoguessr_score").mean().alias("avg"),
        pl.col("geoguessr_score").median().alias("med"),
    )
    .filter(pl.col("n") >= 5)
    .sort("avg", descending=True)
)

print(f"\n  {'country':<30}  {'n':>4}  {'avg':>6}  {'median':>7}")
print(f"  {'-'*30}  {'-'*4}  {'-'*6}  {'-'*7}")
for row in by_country.iter_rows(named=True):
    print(f"  {row['guessed_country']:<30}  {row['n']:>4}  {row['avg']:>6.0f}  {row['med']:>7.0f}")

print(f"\nDone. Charts saved to docs/")
