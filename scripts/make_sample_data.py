"""Generate the synthetic sample in data/sample/ (safe to commit).

The files have exactly the same layout as the real data1.xlsx / data2.xlsx, but
every number is random. A few bad records are planted on purpose so the quality
report shows each rule working:

    data1.xlsx  header/cell swap (repaired), 1 exact duplicate (dropped),
                1 negative trade value and 1 wrong unit (rejected),
                partner Peru has no electricity data (kept with NULLs)
    data2.xlsx  1 negative Solar generation (rejected)

Usage (from the project root):
    uv run python scripts/make_sample_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / "data" / "sample"
YEARS = [2022, 2023, 2024]
rng = np.random.default_rng(751)

PARTNERS = ["Japan", "Korea, Rep.", "United States", "Germany", "Vietnam", "India", "France",
            "Peru"]
COUNTRIES = {"Japan": "JPN", "South Korea": "KOR", "United States": "USA", "Germany": "DEU",
             "Viet Nam": "VNM", "India": "IND", "France": "FRA"}


def make_trade() -> pd.DataFrame:
    rows = []
    for partner in PARTNERS:
        for year in YEARS:
            for flow in ["Export", "Import"]:
                qty = float(rng.integers(500, 200_000))
                rows.append({
                    "China": "China", "TradeFlow": flow, "ProductCode": 284690,
                    "Product Description": "Compounds, inorganic or organic, of rare-earth (SYNTHETIC)",
                    "Year": year, "Partner": partner,
                    "Trade Value 1000USD": round(qty * rng.uniform(0.005, 0.08), 2),
                    "Quantity": qty, "Quantity Unit": "Kg",
                })
    df = pd.DataFrame(rows)
    df.loc[5, "China"] = "Reporter"            # header/cell swap, as in the real file
    df.loc[10, "Trade Value 1000USD"] = -12.5  # rejected: negative value
    df.loc[20, "Quantity Unit"] = "Ton"        # rejected: unit must be kg
    return pd.concat([df, df.iloc[[30]]], ignore_index=True)  # exact duplicate


def make_electricity() -> pd.DataFrame:
    rows = []
    for country, iso in COUNTRIES.items():
        for year in YEARS:
            gen = {s: float(rng.uniform(5, 300)) for s in ["Solar", "Wind", "Hydro", "Coal", "Gas"]}
            net_imports = float(rng.uniform(-20, 20))
            total = sum(gen.values())
            agg = {
                "Wind and solar": gen["Solar"] + gen["Wind"],
                "Renewables": gen["Solar"] + gen["Wind"] + gen["Hydro"],
                "Fossil": gen["Coal"] + gen["Gas"],
                "Total generation": total,
                "Demand": total + net_imports,
            }
            sources = {**{s: (v, False) for s, v in gen.items()},
                       "Net imports": (net_imports, False),
                       **{s: (v, True) for s, v in agg.items()}}
            for source, (twh, is_agg) in sources.items():
                balance = source in ("Net imports", "Demand")
                fossil = source in ("Coal", "Gas", "Fossil")
                emissions = None if balance else round(twh * (0.8 if fossil else 0.02), 3)
                rows.append({
                    "Area": country, "ISO 3 code": iso, "Year": year,
                    "Area type": "Country or economy", "Electricity source": source,
                    "Is aggregated source": is_agg, "Generation (TWh)": round(twh, 3),
                    "Generation YoY change (TWh)": None if year == YEARS[0] else round(rng.normal(0, 5), 3),
                    "Generation YoY change (%)": None if year == YEARS[0] else round(rng.normal(0, 8), 3),
                    "Share of generation (%)": round(twh / total * 100, 3),
                    "Share of generation YoY change (% points)": round(rng.normal(0, 1), 3),
                    "Capacity (GW)": None if balance else round(twh / rng.uniform(2, 6), 2),
                    "Emissions (MtCO2e)": emissions,
                    "Emissions YoY change (MtCO2e)": None,
                    "Emissions YoY change (%)": None,
                    "Share of emissions (%)": None,
                    "Emissions intensity (gCO2e/kWh)": None if balance else (800.0 if fossil else 20.0),
                })
    df = pd.DataFrame(rows)
    df.loc[0, "Generation (TWh)"] = -3.0  # rejected: negative Solar generation
    return df


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    make_trade().to_excel(OUT / "data1.xlsx", sheet_name="By-HS6Product", index=False)
    make_electricity().to_excel(OUT / "data2.xlsx", sheet_name="elec-gen by countries", index=False)
    print(f"Synthetic sample written to {OUT}")


if __name__ == "__main__":
    main()
