# Dashboard: design, install, launch, reproduce, present

The dashboard (Assignment 7) is a local [Streamlit](https://streamlit.io) app that communicates the
project's question, evidence, results and limitations from Assignments 3–6. A reviewer can install it,
launch it and reproduce what it shows from a clean clone, without the restricted source data.

## 1. Install

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/) and Git.

```bash
git clone https://github.com/bolorbud-gif/business-analytics-portfolio.git
cd business-analytics-portfolio
uv sync
```

`uv sync` installs the exact versions in `uv.lock`, Streamlit included.

## 2. Launch

```bash
uv run python scripts/deploy.py run
```

Open <http://localhost:8501>. (Equivalent: `uv run streamlit run src/dashboard/app.py`.) Stop it with
Ctrl+C. Use `--port 8502` if 8501 is taken.

## 3. Design

### The one conclusion the dashboard must make clear

> **Country size, not wind, drives demand for Chinese rare-earth compounds.** Countries with more wind
> do import more (10x the wind capacity, about 8.7x the imports), but at the same size 10x the wind goes
> with only about 1.6x the imports, and the 95% interval (0.8x to 3.3x) includes no effect; 10x the size
> goes with about 55x.
>
> **The decision it supports:** size a country's demand for rare-earth compounds, and rank markets, by
> the scale of its power system, not by its wind targets. Treat wind's own effect as unproven, not as zero.

Everything else on the dashboard either supports this conclusion, puts it to work, or qualifies it.

### Page hierarchy (sketched before the pages were built)

```
Start here
└── The answer  (primary page)           the conclusion, the evidence in one chart, what it means
The case  (the primary user path)
├── 1 · Why: wind or size?               imports vs wind, with and without size; H1–H5; robustness
└── 2 · What to do                       an action for every country; the 2025 forecast
More detail  (secondary views)
├── Market evidence                      who buys, the fixed-volume price fall, the wind build-out
├── Predictive engine                    validation against the baseline, uncertainty, threshold explorer
└── Data and pipeline                    sources, coverage, quality checks, the analysis sample
About
└── Limitations and reproducibility      limits, provenance of every number, how to reproduce
```

The primary page and the two-step path were built and tested first. Each page on the path ends with a
link to the next one (*The answer → Why → What to do → Limitations*); the secondary views add depth for
readers who want it.

### Page layout

- **KPIs first.** *The answer* puts four tiles directly under the conclusion, visible without scrolling:
  imports for 10x wind at the same size (1.6x, interval includes 1x), for 10x size (55x), the top-5
  buyers' share (83%) and the engine's major-buyer ranking (AUC). The evidence pages open with their own
  KPI rows.
- **Filters in the sidebar.** Each page's filters sit in the sidebar under **Filters**, below the page
  list, and apply to the page; a caption under them says what they leave unchanged (the pre-specified
  hypothesis tests, the engine's own test scores). On *Why: wind or size?* the regressions are refitted
  on the country-years the filters keep. Defaults show everything (all years and size groups, the latest
  year, the engine's own cost ratio and threshold), so each page is useful on first load.
- **Data freshness.** Under every title, and in the sidebar: the years of China's trade records and of
  its exports by buyer, the last year of Ember power data, and when (and from which commit) the results
  were built.
- **Charts.** Every chart is drawn through `components.show()`, which refuses a chart without a title;
  every axis is titled with its unit or scale (kg, tonnes, GW, %, times, log scale).

### Data-access layer

The app never queries the database or trains a model. [`src/dashboard/data.py`](../src/dashboard/data.py)
builds a **results snapshot** from two sources and the app only reads that snapshot:

| Source | Read through | Gives the dashboard |
|---|---|---|
| Assignment 4 database (`data/processed/rare_earth.db`) | `database_tables()`, using the Assignment 5 functions in `src/analysis` | Sample, quality checks, concentration, prices, wind trend, H1–H5, models, robustness |
| Assignment 6 result artifact, the saved engine bundle (`models/rare_earth_engine.joblib`) | `load_engine_artifact()` and `engine_tables()` | Cross-validation, test scores with bootstrap intervals, test predictions, out-of-fold scores, plus the actions and the forecast made with the saved pipelines (nothing is retrained) |

The app loads the snapshot once per build (`st.cache_data`, keyed on the folder and its build time)
and loads no model at runtime: the engine artifact is read by `scripts/deploy.py` when the snapshot is
built. What the app computes on the fly also calls the earlier assignments' code, cached the same way:
the refitted regressions use `src.analysis.statistical` (Assignment 5) and the threshold explorer
`src.modeling.evaluate` (Assignment 6). The colours come from `src.analysis.palette`, shared with the
report charts. Nothing is copied: a test checks that the dashboard redefines no colour and that it starts
without loading Matplotlib, Seaborn, statsmodels or Pandera.

| Snapshot | Folder | In git |
|---|---|---|
| Real results | `data/published/` | Yes (results derived from the restricted data, at country level, published by the author's decision) |
| Synthetic results | `data/processed/published_sample/` | No (rebuilt on demand) |

### Uncertainty, sample, provenance and limitations

Every evidence page ends with an **About these numbers** block that states the **sample** behind the
page, the **uncertainty** of its numbers (95% intervals clustered by country, cross-validation standard
deviations, bootstrap intervals that resample whole countries, Holm-corrected p-values), their
**provenance** (the snapshot tables, the data fingerprint and git commit, and for the engine pages the
artifact's training date, commit and `random_state`) and its **limitations**. The last page gathers the
limitations and the full provenance table.

### Empty and error states

| Situation | What the reader sees |
|---|---|
| No snapshot, or an incomplete or unreadable one | A plain message naming what is missing and the one command that rebuilds it; the app stops cleanly |
| No real database when rebuilding (`deploy.py build` or `check`) | A message saying where the source files go and the command that builds the database; the synthetic route needs no database |
| A table in the snapshot can't be drawn (for example an old snapshot missing a column) | An error on that page only, with the fix and the technical details folded away; every other page keeps working |
| Filters that leave nothing to show (no year or size group chosen, a country search with no match) | A note saying why nothing is shown and what to change in the sidebar |
| Filters that leave too few country-years to refit the regressions (under 12, or under 6 countries) | A note giving the minimum; the chart and the tables that don't need a refit still show |
| A synthetic snapshot | A warning on every page that the numbers are fake |

`tests/test_dashboard.py` covers each case.

## 4. Reproduce the displayed results

### Without the restricted data (any reviewer)

```bash
uv run python scripts/deploy.py run --sample
```

This rebuilds the whole chain from the committed synthetic sample: the pipeline builds
`rare_earth_sample.db`, the engine is trained on synthetic data and saved
(`models/rare_earth_engine_synthetic.joblib`), the snapshot is built from both (about 3 minutes in
all), and the dashboard opens on it, with a warning that the numbers are fake. Two separate builds give
identical snapshots: every step is seeded (`random_state` in
[`config/model_params.yaml`](../config/model_params.yaml)). Add `--rebuild` to force a fresh build.

### With the real data (authorized users)

1. Put `data1.xlsx` and `data2.xlsx` in `data/raw/` ([setup.md](setup.md)) and build the database:

   ```bash
   uv run python scripts/run_pipeline.py
   ```

2. Retrain the engine and rebuild the snapshot in a temporary folder, then compare with the committed
   snapshot:

   ```bash
   uv run python scripts/deploy.py check
   ```

   It prints `OK: the committed snapshot matches a fresh build from the real data.` and exits 0, or
   lists every number that differs and exits 1. Build times, git commits and library versions are
   ignored; numbers are compared to a relative tolerance of 10⁻⁶.

3. To replace the committed snapshot after the data change: `uv run python scripts/deploy.py build`
   (add `--retrain` to retrain the engine artifact first).

### Automated checks

```bash
uv run pytest tests/test_dashboard.py
```

The tests build a snapshot from the synthetic sample, open every page headlessly on both the committed
and the synthetic snapshot, and check each page's notes, freshness caption, chart titles and sidebar
filters, the empty and error states (missing database included), the committed snapshot's files and
headline numbers, and rehearse the presentation path below.

## 5. Presentation path (rehearsed)

About 6 minutes. The app is launched beforehand with `uv run python scripts/deploy.py run` and opens on
*The answer*.

| # | Page | Do | Say (the point to land) | Time |
|---|---|---|---|---|
| 1 | The answer | Read the boxed conclusion; point at the chart | "Countries with more wind buy more rare earths, 8.7x per 10x wind. But at the same size it's 1.6x, and the interval crosses 1x: no proven effect. Size is 55x. So plan demand from size, not wind targets." | 1:30 |
| 2 | 1 · Why: wind or size? | Show the scatter coloured by size; in the sidebar, switch on **Remove country size** | "Large countries sit top-right: size drives both. Remove size and the cloud goes flat, r = 0.13." Then the H1–H5 table: "H1 and H5 supported; H2, wind at the same size, not." | 1:30 |
| 3 | 2 · What to do | In the sidebar, keep Approach, Grow, Verify; type *India*, then clear | "The engine turns this into actions: India buys a fraction of what its power sector suggests, so Grow; the Netherlands buys hundreds of times more, a trading hub, so Verify." Then the 2025 forecast | 1:30 |
| 4 | Predictive engine (optional) | In the sidebar, move the cost slider from 3 to 0.25 | "On countries it never saw, estimates are typically within about 11x, against 36x for a naive guess, and major buyers rank well, AUC 0.95. If a false alarm cost more than a missed buyer, the threshold would rise from 0.25 to 0.80." | 1:00 |
| 5 | Limitations and reproducibility | Point at the limitations and the provenance table | "Two years, compounds only, associations not causes. Every number here is rebuilt and checked by one command, from this commit and this data fingerprint." | 0:30 |

**Fallbacks.** Port taken: `--port 8502`. App won't start: `uv sync`, then run again. No time for step 4:
skip it; steps 1–3 and 5 carry the argument. No live demo at all: the same numbers are in
[the report](statistical_analysis_report.md) and its figures.

**Rehearsal record.** The path is rehearsed automatically by
`tests/test_dashboard.py::test_presentation_path_rehearsal`. It opens each page and checks the facts
spoken above: the conclusion, r = 0.13 after removing size, the H1–H5 results, India *Grow* and the
Netherlands *Verify*, and the threshold moving to 0.80. It was also walked through by hand in the
browser before the final push.

### The ninety-second test

A person who hasn't seen the project gets the app, open on *The answer*, for 90 seconds, with no help.
Then the laptop is closed and they are asked:

1. What question does the dashboard answer?
2. What is the answer?
3. What should a rare-earth supplier do about it?
4. How sure is it, and what is its main limit?

It passes when questions 1–3 are answered correctly in their own words (*does wind drive demand for
Chinese rare earths? No, country size does; size demand by a country's power system, not its wind
targets*) and question 4 mentions that wind's own effect is unproven or that there are only two years
of export data. Anything they found confusing is fixed and the test repeated with someone new.

| Date | Tester | Q1 | Q2 | Q3 | Q4 | Passed | Confusing | Change made |
|---|---|---|---|---|---|---|---|---|
| | | | | | | | | |

## 6. Dashboard checklist

| Item | Where it is met |
|---|---|
| Three to five KPIs visible without scrolling | *The answer*: four tiles under the conclusion (section 3, page layout) |
| At least one trend view and one breakdown view | Trend: installed wind capacity by year (*Market evidence → Wind build-out*). Breakdowns: buyers' shares, price change by buyer, the forecast by country, the scatter by size group |
| Filters in the sidebar, applying to the whole page | Every page's filters are in the sidebar; a test checks that no filter is in the page body |
| Sensible defaults | Everything shown on first load; the latest year; the engine's own cost ratio and threshold |
| Data-freshness caption | Under every title and in the sidebar |
| Every chart titled, axes labelled with units | `components.show()` requires a title; a test checks every chart on every page |
| Empty-filter and missing-database cases | Section 3, empty and error states |
| Caching on all data loads and model loads | `st.cache_data` on the snapshot, the refits and the threshold explorer; no model is loaded at runtime |
| Imports from the Assignment 4, 5 and 6 modules | The snapshot is built with `src.analysis` and `src.modeling`; the app's refits and threshold explorer call them too |
| All paths relative, none absolute | Paths are built from the project root; the docs, notebook outputs and the provenance table show none from this machine |
| Someone else has opened it and passed the ninety-second test | Section 5, the ninety-second test |

## 7. Deployment

The app runs locally. Public hosting and Docker are optional for this assignment and aren't set up (the
`docker/` files are the course template's placeholders). Any service that runs
`streamlit run src/dashboard/app.py` from this repository would work, because the committed snapshot
makes the app independent of the database.
