# Real Exchange Rate App

Streamlit app that computes the real exchange rate (RER) between any two IMF countries (or the Euro area) using monthly IMF CPI and exchange-rate data from January 1976 where available.

## Definitions

- **S(t)**: units of Country 2 currency per 1 unit of Country 1 currency, built from IMF period-average rates (local currency per USD): S = FX2 / FX1.
- **P1(t), P2(t)**: monthly CPI of Country 1 and Country 2 (Euro area uses HICP).
- **RER(t) = S(t) × P1(t) / P2(t)**
- **RER\***: average RER(t) over valid months in the selected sample.
- **Real Index(t) = 100 × RER(t) / RER\***, recalculated whenever the sample changes.

## Features

- Country selectors from the IMF country codelist plus Euro area (G163)
- Sample start/end month selector
- Real, Nominal (actual currency units), or Both (separate axes) interactive charts
- CSV download of all observations and calculations in the selected sample

## Data

IMF SDMX 3.0 API: `https://api.imf.org/external/sdmx/3.0`

- CPI: `{ISO3}.CPI._T.IX.M` (falls back to `{ISO3}.HICP._T.IX.M`)
- Exchange rate: `{ISO3}.XDC_USD.PA_RT.M`

IMF data may have gaps or limited coverage. Live downloads can occasionally fail; reload the app if so.

## Run

Python 3.12. `pip install -r requirements.txt` then `streamlit run app.py`. Deployed on Streamlit Community Cloud.
