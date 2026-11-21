"""Exploratory data analysis package for the rare-earth / wind-power database.

Three modules, each usable on its own:

- ``exploratory``: connect to the database, run data-quality checks, load analysis
  frames, describe distributions and market concentration.
- ``statistical``: correlation, partial correlation, log-log regression, hypothesis tests
  (normality, paired change, group comparison, bootstrap, Holm correction) and
  regression diagnostics.
- ``charts``: the visualization suite (Matplotlib + Seaborn) in one consistent style, with
  its colours in ``palette`` (shared with the dashboard).

Typical use::

    from src.analysis import exploratory as ex, statistical as st, charts as ch
    con, path = ex.open_database()
    panel = ex.load_country_panel(con)
    st.partial_correlation(ex.analysis_sample(panel), "imports_from_china_kg",
                           "wind_capacity_gw", ["total_generation_twh"])

Function reference: docs/api_reference.md.
"""

import importlib

__all__ = ["charts", "exploratory", "statistical"]


def __getattr__(name):
    """Load a module on first use (``src.analysis.charts``), so importing one module, such as the
    palette in the dashboard, doesn't load Matplotlib, Seaborn, statsmodels and Pandera."""
    if name in __all__ or name == "palette":
        return importlib.import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
