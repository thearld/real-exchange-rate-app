"""Real Exchange Rate (RER) app using IMF SDMX 3.0 data.

S(t)  = units of Country 2 currency per 1 unit of Country 1 currency
RER(t) = S(t) * P1(t) / P2(t)
Real Index(t) = 100 * RER(t) / RER*, where RER* = mean RER(t) over the selected sample
"""

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

BASE = "https://api.imf.org/external/sdmx/3.0"
HEADERS = {
    "Accept": "application/vnd.sdmx.data+json;version=2.0.0",
    "User-Agent": "real-exchange-rate-app/1.0 (Streamlit)",
}
START = "1976-01"
EURO_AREA = "G163"

# Irrevocable euro conversion rates (legacy currency units per EUR).
# IMF reports euro-member exchange rates in legacy currency only up to euro
# adoption; after that the euro-area (G163) rate is used. Legacy rates are
# divided by these factors so the whole series is in EUR per USD.
EURO_CONVERSION = {
    "AUT": 13.7603, "BEL": 40.3399, "DEU": 1.95583, "ESP": 166.386,
    "FIN": 5.94573, "FRA": 6.55957, "IRL": 0.787564, "ITA": 1936.27,
    "LUX": 40.3399, "NLD": 2.20371, "PRT": 200.482, "GRC": 340.75,
    "SVN": 239.64, "CYP": 0.585274, "MLT": 0.4293, "SVK": 30.126,
    "EST": 15.6466, "LVA": 0.702804, "LTU": 3.4528, "HRV": 7.5345,
}

st.set_page_config(page_title="Real Exchange Rate App", layout="wide")


# ---------------------------------------------------------------- data access
def fetch_series(dataflow: str, key: str) -> pd.Series:
    """Return a monthly pd.Series (index = month-start Timestamp) or empty Series."""
    url = (
        f"{BASE}/data/dataflow/IMF.STA/{dataflow}/+/{key}"
        "?dimensionAtObservation=TIME_PERIOD&attributes=dsd&measures=all"
    )
    r = requests.get(url, headers=HEADERS, timeout=60)
    if r.status_code == 404:
        return pd.Series(dtype=float)
    r.raise_for_status()
    data = r.json().get("data", {})
    datasets = data.get("dataSets") or []
    if not datasets or not datasets[0].get("series"):
        return pd.Series(dtype=float)
    periods = data["structures"][0]["dimensions"]["observation"][0]["values"]
    series = next(iter(datasets[0]["series"].values()))
    rows = {}
    for idx, obs in series.get("observations", {}).items():
        value = obs[0] if isinstance(obs, list) else obs
        if value in (None, "", "NaN"):
            continue
        period = periods[int(idx)]["value"]  # e.g. "1976-M01"
        rows[pd.Timestamp(period.replace("-M", "-") + "-01")] = float(value)
    s = pd.Series(rows, dtype=float).sort_index()
    return s[s.index >= pd.Timestamp(START + "-01")]


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_cpi(iso3: str) -> pd.Series:
    s = fetch_series("CPI", f"{iso3}.CPI._T.IX.M")
    if s.empty:  # Euro area (and some others) publish HICP instead of CPI
        s = fetch_series("CPI", f"{iso3}.HICP._T.IX.M")
    return s


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def get_fx_per_usd(iso3: str) -> pd.Series:
    """Local currency units per USD, period average."""
    if iso3 == "USA":
        return pd.Series(dtype=float)  # handled as 1.0 below
    s = fetch_series("ER", f"{iso3}.XDC_USD.PA_RT.M")
    if iso3 in EURO_CONVERSION:
        s = s / EURO_CONVERSION[iso3]
        ea = fetch_series("ER", f"{EURO_AREA}.XDC_USD.PA_RT.M")
        if not ea.empty:
            after = ea[ea.index > s.index.max()] if not s.empty else ea
            s = pd.concat([s, after]).sort_index()
    return s


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def get_countries() -> dict:
    """Return {display name: ISO3} from the IMF country codelist."""
    try:
        r = requests.get(
            f"{BASE}/structure/codelist/IMF/CL_COUNTRY/+",
            headers={**HEADERS, "Accept": "application/vnd.sdmx.structure+json;version=2.0.0"},
            timeout=60,
        )
        r.raise_for_status()
        codes = r.json()["data"]["codelists"][0]["codes"]
        out = {}
        for c in codes:
            cid = c["id"]
            if (len(cid) == 3 and cid.isalpha() and cid.isupper()) or cid == EURO_AREA:
                name = c.get("name") or c.get("names", {}).get("en") or cid
                out[f"{name} ({cid})"] = cid
    except Exception:
        out = {
            "United Kingdom (GBR)": "GBR", "United States (USA)": "USA",
            "Japan (JPN)": "JPN", "Canada (CAN)": "CAN", "China (CHN)": "CHN",
            "Mexico (MEX)": "MEX", "Germany (DEU)": "DEU", "Switzerland (CHE)": "CHE",
        }
    out = {k: v for k, v in out.items() if v != EURO_AREA}
    out["Euro area (G163)"] = EURO_AREA
    return dict(sorted(out.items()))


def fx_or_one(iso3: str, index: pd.DatetimeIndex) -> pd.Series:
    if iso3 == "USA":
        return pd.Series(1.0, index=index)
    return get_fx_per_usd(iso3).reindex(index)


# ------------------------------------------------------------------------- UI
st.title("Real Exchange Rate (RER) App")
st.caption(
    "Data: IMF SDMX 3.0 API (monthly CPI and period-average exchange rates per USD). "
    "S(t) = Country 2 currency per 1 unit of Country 1 currency. "
    "RER(t) = S(t) × P1(t) / P2(t)."
)

countries = get_countries()
names = list(countries.keys())


def default_index(iso3: str) -> int:
    for i, n in enumerate(names):
        if countries[n] == iso3:
            return i
    return 0


c1, c2 = st.columns(2)
name1 = c1.selectbox("Country 1 (base currency)", names, index=default_index("GBR"))
name2 = c2.selectbox("Country 2 (quote currency)", names, index=default_index("USA"))
iso1, iso2 = countries[name1], countries[name2]

if iso1 == iso2:
    st.warning("Choose two different countries.")
    st.stop()

with st.spinner("Downloading IMF data..."):
    try:
        p1, p2 = get_cpi(iso1), get_cpi(iso2)
        idx = p1.index.union(p2.index)
        if iso1 != "USA":
            idx = idx.union(get_fx_per_usd(iso1).index)
        if iso2 != "USA":
            idx = idx.union(get_fx_per_usd(iso2).index)
        e1, e2 = fx_or_one(iso1, idx), fx_or_one(iso2, idx)
    except Exception as exc:
        st.error(f"IMF data download failed: {exc}. Please try again in a few minutes.")
        st.stop()

df = pd.DataFrame(index=idx)
df.index.name = "Month"
df["FX1_LCU_per_USD"] = e1
df["FX2_LCU_per_USD"] = e2
df["S_Country2_per_Country1"] = df["FX2_LCU_per_USD"] / df["FX1_LCU_per_USD"]
df["P1_CPI"] = p1.reindex(idx)
df["P2_CPI"] = p2.reindex(idx)
df["RER"] = df["S_Country2_per_Country1"] * df["P1_CPI"] / df["P2_CPI"]

valid = df.dropna(subset=["RER"])
if valid.empty:
    st.error(
        f"No overlapping monthly CPI and exchange-rate data for {name1} and {name2}. "
        "IMF coverage may be limited for one of these countries."
    )
    st.stop()

first, last = valid.index.min().date(), valid.index.max().date()
months = pd.date_range(first, last, freq="MS")
labels = [m.strftime("%Y-%m") for m in months]
start_lbl, end_lbl = st.select_slider(
    "Sample period (start and end month)", options=labels, value=(labels[0], labels[-1])
)
start, end = pd.Timestamp(start_lbl + "-01"), pd.Timestamp(end_lbl + "-01")
if start > end:
    st.warning("Start month must be before end month.")
    st.stop()

sample = df.loc[start:end].copy()
valid_sample = sample["RER"].dropna()
if valid_sample.empty:
    st.error("No valid RER observations in the selected period.")
    st.stop()

rer_star = valid_sample.mean()
sample["RER_star"] = rer_star
sample["Real_Index"] = 100 * sample["RER"] / rer_star

view = st.radio("Chart", ["Real", "Nominal", "Both"], horizontal=True)
unit = f"{iso2} currency per 1 {iso1} currency"

fig = go.Figure()
if view in ("Real", "Both"):
    fig.add_trace(go.Scatter(x=sample.index, y=sample["Real_Index"], name="Real Index (avg = 100)",
                             mode="lines", line=dict(color="#1f77b4")))
if view in ("Nominal", "Both"):
    fig.add_trace(go.Scatter(x=sample.index, y=sample["S_Country2_per_Country1"], name=f"Nominal S(t) ({unit})",
                             mode="lines", line=dict(color="#d62728"),
                             yaxis="y2" if view == "Both" else "y"))

layout = dict(hovermode="x unified", height=520, legend=dict(orientation="h", y=-0.15),
              margin=dict(l=40, r=40, t=40, b=40), xaxis=dict(title="Month"))
if view == "Real":
    layout["yaxis"] = dict(title="Real Index (sample avg = 100)")
elif view == "Nominal":
    layout["yaxis"] = dict(title=f"S(t): {unit}")
else:
    layout["yaxis"] = dict(title="Real Index (sample avg = 100)", color="#1f77b4")
    layout["yaxis2"] = dict(title=f"S(t): {unit}", overlaying="y", side="right", color="#d62728")
fig.update_layout(**layout, title=f"{name1} vs {name2}")
st.plotly_chart(fig, width="stretch")

m1, m2, m3 = st.columns(3)
m1.metric("RER* (sample average RER)", f"{rer_star:,.4f}")
m2.metric("Valid months in sample", f"{valid_sample.size}")
m3.metric("Mean Real Index (check = 100)", f"{sample['Real_Index'].mean():.4f}")

st.subheader("Data")
st.dataframe(sample, width="stretch")

csv = sample.reset_index()
csv["Month"] = csv["Month"].dt.strftime("%Y-%m")
csv.insert(1, "Country1", iso1)
csv.insert(2, "Country2", iso2)
st.download_button(
    "Download CSV (selected sample)",
    data=csv.to_csv(index=False).encode("utf-8"),
    file_name=f"rer_{iso1}_{iso2}_{start_lbl}_{end_lbl}.csv",
    mime="text/csv",
)

st.caption(
    "Notes: FX columns are IMF period-average local currency units per USD (USD = 1). "
    "Euro-member legacy rates are converted to EUR at the irrevocable conversion rate and "
    "spliced with the euro-area rate after adoption. Euro area uses HICP when CPI is not "
    "published. Months with missing data are excluded from RER*. "
    f"Retrieved {dt.date.today():%Y-%m-%d}."
)
