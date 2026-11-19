# API Reference

Generated from the docstrings by `scripts/build_api_reference.py`; do not edit by hand.
Every function below is importable, e.g. `from src.analysis import statistical as st`.

## `src.analysis`

Exploratory data analysis package for the rare-earth / wind-power database.

### `src.analysis.exploratory`

Exploratory analysis: open the Assignment 4 database, check its quality, describe the data.

- **`analysis_sample`** `def analysis_sample(panel: pandas.DataFrame) -> pandas.DataFrame`
  Country-years usable for the multivariate analysis: imports, wind capacity and total generation all recorded and positive (so logs exist). Adds a size tercile.
- **`check_database`** `def check_database(con) -> pandas.DataFrame`
  Run data-quality checks on the database. One row per check: check, passed, detail.
- **`concentration`** `def concentration(values: pandas.Series) -> dict`
  Market concentration of a set of values (e.g. kg bought per country).
- **`coverage_by_year`** `def coverage_by_year(con) -> pandas.DataFrame`
  Number of trade rows per year and direction: shows which years each direction covers.
- **`describe_numeric`** `def describe_numeric(df: pandas.DataFrame, columns: list[str]) -> pandas.DataFrame`
  Univariate summary: count, missing, centre, spread and skew for each column.
- **`load_country_panel`** `def load_country_panel(con) -> pandas.DataFrame`
  One row per partner country and year: imports from China, growth, wind, and size.
- **`load_trade`** `def load_trade(con) -> pandas.DataFrame`
  Every trade row with the partner's power mix (view partner_trade_energy).
- **`load_wind`** `def load_wind(con) -> pandas.DataFrame`
  Wind generation and capacity per country and year.
- **`market_shares`** `def market_shares(df: pandas.DataFrame, by: str, value: str, top: int = 10) -> pandas.DataFrame`
  Each group's share of the total, largest first; groups after `top` folded into one row.
- **`open_database`** `def open_database(path=None)`
  Open the database with foreign keys ON. Returns (connection, path).
- **`period_change`** `def period_change(yearly: pandas.DataFrame, trade_flow: str, start: int, end: int) -> pandas.Series`
  Percent change in quantity, value and unit value between two years for one direction.
- **`yearly_trade`** `def yearly_trade(trade: pandas.DataFrame) -> pandas.DataFrame`
  Totals per year and direction, with the average unit value (total value / total kg).

### `src.analysis.statistical`

Statistical analysis: correlation, partial correlation, regression and growth summaries.

- **`bootstrap_ci`** `def bootstrap_ci(values, statistic, n_boot: int = 2000, level: float = 0.95, seed: int = 0) -> dict`
  Percentile bootstrap confidence interval for any statistic of a 1-D sample.
- **`compare_groups`** `def compare_groups(df: pandas.DataFrame, value: str, group: str, order: list | None = None) -> dict`
  Kruskal-Wallis test: do the groups' distributions differ? (no normality assumed)
- **`correlation`** `def correlation(df: pandas.DataFrame, x: str, y: str, method: str = 'spearman') -> dict`
  Correlation between two columns over rows where both are present.
- **`correlation_matrix`** `def correlation_matrix(df: pandas.DataFrame, columns: list[str], method: str = 'spearman') -> pandas.DataFrame`
  Pairwise correlation matrix of the columns (Spearman by default).
- **`correlation_table`** `def correlation_table(df: pandas.DataFrame, pairs: list[tuple[str, str]], method: str = 'spearman') -> pandas.DataFrame`
  correlation() for several column pairs, one row each.
- **`fit_log_ols`** `def fit_log_ols(df: pandas.DataFrame, y: str, xs: list[str], year_effects: bool = True, cluster: str | None = 'partner')`
  OLS of log10(y) on log10(xs), with optional year fixed effects.
- **`growth_summary`** `def growth_summary(growth_pct: pandas.Series, extreme: float = 500.0) -> dict`
  Summary of percentage growth rates. Rates from tiny bases explode, so the median and interquartile range are reported instead of the mean.
- **`hypothesis_table`** `def hypothesis_table(tests: list[dict], alpha: float = 0.05) -> pandas.DataFrame`
  Collect hypothesis tests and adjust for testing several at once (Holm method).
- **`log10_positive`** `def log10_positive(s: pandas.Series) -> pandas.Series`
  log10 of the positive values; zero or negative becomes NaN (log is undefined).
- **`normality_test`** `def normality_test(values: pandas.Series, log: bool = False, alpha: float = 0.05) -> dict`
  Shapiro-Wilk test of normality (on log10 values if log=True). Low p = not normal.
- **`paired_change`** `def paired_change(df: pandas.DataFrame, entity: str, period: str, value: str, start, end) -> dict`
  Wilcoxon signed-rank test on the change of `value` for entities seen in both periods.
- **`partial_correlation`** `def partial_correlation(df: pandas.DataFrame, x: str, y: str, controls: list[str], log: bool = True) -> dict`
  Correlation of x and y after removing what the controls explain.
- **`regression_diagnostics`** `def regression_diagnostics(result) -> pandas.DataFrame`
  Assumption checks for an OLS result: unequal variance, residual normality, collinearity.
- **`residualize`** `def residualize(df: pandas.DataFrame, column: str, controls: list[str]) -> pandas.Series`
  What is left of `column` after a linear fit on the controls (with intercept).
- **`strength`** `def strength(r: float) -> str`
  Plain-language size of a correlation coefficient.
- **`tidy_coefficients`** `def tidy_coefficients(result) -> pandas.DataFrame`
  Coefficient table: estimate, standard error, p-value and 95% interval.
- **`top_share`** `def top_share(values, k: int = 5) -> float`
  Share of the total held by the k largest values.

### `src.analysis.charts`

Charts for the exploratory analysis (Matplotlib + Seaborn).

- **`apply_style`** `def apply_style() -> None`
  Seaborn theme with the project's colours and recessive grid (applies to Matplotlib too).
- **`change_bars`** `def change_bars(changes: pandas.Series, title: str, subtitle: str, source: str)`
  Percent changes as bars: blue up, red down, from a zero baseline.
- **`coefficient_plot`** `def coefficient_plot(models: dict[str, pandas.DataFrame], terms: dict[str, str], title: str, subtitle: str, source: str, xlabel: str = 'Elasticity (95% CI)')`
  Estimates with 95% intervals for selected terms, one colour per model.
- **`confounding_scatter`** `def confounding_scatter(raw: pandas.DataFrame, x: str, y: str, group: str, group_order: list[str], partial: pandas.DataFrame, raw_title: str, partial_title: str, title: str, subtitle: str, source: str, xlabel: str, ylabel: str)`
  Two panels: the raw log-log relationship coloured by a size group, then the same relationship after removing size (residuals).
- **`correlation_heatmap`** `def correlation_heatmap(matrix: pandas.DataFrame, labels: list[str], title: str, subtitle: str, source: str)`
  Correlation matrix (lower triangle) on a blue (positive) / gray (zero) / red scale.
- **`group_strip`** `def group_strip(df: pandas.DataFrame, value: str, group: str, order: list[str], ylabel: str, title: str, subtitle: str, source: str, tick_labels: list[str] | None = None)`
  Every observation per group on a log scale, with the median marked.
- **`line_trend`** `def line_trend(df: pandas.DataFrame, x: str, series: list[str], labels: list[str], ylabel: str, title: str, subtitle: str, source: str)`
  Up to three lines on one axis, each labelled at its end and in the legend.
- **`log_histogram`** `def log_histogram(values: pandas.Series, xlabel: str, title: str, subtitle: str, source: str, bins: int = 20)`
  Histogram with log-spaced bins, for right-skewed positive values.
- **`market_share_bars`** `def market_share_bars(shares: pandas.DataFrame, title: str, subtitle: str, source: str)`
  Horizontal bars of each country's share (output of exploratory.market_shares).
- **`pair_plot`** `def pair_plot(df: pandas.DataFrame, columns: list[str], labels: list[str], hue: str, hue_order: list[str], title: str, subtitle: str, source: str)`
  Seaborn pair plot of log10 values: every pairwise relationship at once, coloured by group.
- **`save`** `def save(fig, name: str, folder: pathlib.Path = WindowsPath('C:/Users/mcobp/business-analytics-portfolio/docs/figures')) -> pathlib.Path`
  Save a figure as PNG (150 dpi) in docs/figures/ or another folder; returns the path.

## `src.data_pipeline`

ETL pipeline: extract raw Excel files, transform, validate, load into SQL.

### `src.data_pipeline.pipeline`

End-to-end pipeline, importable from notebooks and tests.

- **`describe_views`** `def describe_views(views: dict[str, pandas.DataFrame], trade: pandas.DataFrame, report: src.data_pipeline.quality.QualityReport) -> None`
  Add plain-language notes about gaps in the analysis views to the report.
- **`export`** `def export(views: dict[str, pandas.DataFrame], export_dir: pathlib.Path) -> None`
  Save the analysis views as CSV (and Excel). Runs after the database is saved.
- **`run_pipeline`** `def run_pipeline(raw_dir, sources: dict[str, str], database_url: str, report_path=None, rejected_dir='data/interim', max_rejected_pct: float = 5.0, rebuild: bool = False, echo: bool = False, export_dir=None) -> src.data_pipeline.quality.QualityReport`
  Extract -> transform -> validate -> normalize -> load. Builds or refreshes the database.

### `src.data_pipeline.extract`

Extract stage: read the raw Excel files from data/raw/.

- **`extract`** `def extract(raw_dir: pathlib.Path, sources: dict[str, str]) -> dict[str, pandas.DataFrame]`
  Read every configured source file. Returns {source name: raw DataFrame}.
- **`read_excel`** `def read_excel(path: pathlib.Path) -> pandas.DataFrame`
  Read the first sheet of an Excel file, with a clear error if it is missing.

### `src.data_pipeline.transform`

Transform stage: clean column names, fix known data problems, normalize to 3NF.

- **`normalize`** `def normalize(trade: pandas.DataFrame, electricity: pandas.DataFrame, report: src.data_pipeline.quality.QualityReport | None = None) -> dict[str, pandas.DataFrame]`
  Split the validated source tables into 3NF tables.
- **`transform_electricity`** `def transform_electricity(raw: pandas.DataFrame, report: src.data_pipeline.quality.QualityReport | None = None) -> pandas.DataFrame`
  Rename electricity columns to snake_case.
- **`transform_trade`** `def transform_trade(raw: pandas.DataFrame, report: src.data_pipeline.quality.QualityReport | None = None) -> pandas.DataFrame`
  Clean the rare-earth trade table.

### `src.data_pipeline.validate`

Validate stage: Pandera schemas that every table must pass before loading.

- **`validate_table`** `def validate_table(name: str, df: pandas.DataFrame, report: src.data_pipeline.quality.QualityReport | None = None, rejected_dir: pathlib.Path | None = None, max_rejected_pct: float = 5.0) -> pandas.DataFrame`
  Validate one table and return only the rows that pass.
- **`validate_view`** `def validate_view(name: str, df: pandas.DataFrame) -> None`
  Check a view's rows. Views are computed from validated data, so any failure means the view logic is wrong: stop the run (the load rolls back).

### `src.data_pipeline.load`

Load stage: the normalized (3NF) schema in SQLAlchemy, loading, and the analysis views.

- **`connect`** `def connect(db_path) -> sqlite3.Connection`
  Open the SQLite file with plain sqlite3 (e.g. in a notebook) with foreign keys ON.
- **`create_schema`** `def create_schema(engine: sqlalchemy.engine.base.Engine, rebuild: bool = False) -> None`
  Create all tables if they do not exist yet (views are created by load()).
- **`get_engine`** `def get_engine(url: str, echo: bool = False) -> sqlalchemy.engine.base.Engine`
  Create a SQLAlchemy engine. For SQLite, make sure the folder exists.
- **`load`** `def load(engine: sqlalchemy.engine.base.Engine, tables: dict[str, pandas.DataFrame], report: src.data_pipeline.quality.QualityReport | None = None) -> dict[str, pandas.DataFrame]`
  Replace the contents of every table and refresh the views, in one transaction.
- **`snapshot`** `def snapshot(conn: sqlalchemy.engine.base.Connection, name: str, key: list[str])`
  Rows of a table or view sorted by key, their count and a short content checksum.

### `src.data_pipeline.views`

Analysis views over the normalized (3NF) tables.

- **`create_views`** `def create_views(conn: sqlalchemy.engine.base.Connection) -> None`
  (Re)create every view so its definition always matches this code.
- **`drop_views`** `def drop_views(conn: sqlalchemy.engine.base.Connection) -> None`
- **`view_ddl`** `def view_ddl() -> list[str]`

### `src.data_pipeline.quality`

Data quality tracking: what came in, what was fixed, dropped, rejected and loaded.

- **`QualityReport`** `class QualityReport(raw_dir: str, database: str, started_at: str = <factory>, status: str = 'RUNNING', tables: dict[str, src.data_pipeline.quality.TableQuality] = <factory>, notes: list[str] = <factory>) -> None`
  QualityReport(raw_dir: str, database: str, started_at: str = <factory>, status: str = 'RUNNING', tables: dict[str, src.data_pipeline.quality.TableQuality] = <factory>, notes: list[str] = <factory>)
- **`TableQuality`** `class TableQuality(name: str, source: str, rows_in: int = 0, rows_repaired: int = 0, repairs: list[str] = <factory>, duplicates_dropped: int = 0, rejected_by_reason: collections.Counter = <factory>, rows_rejected: int = 0, rows_valid: int = 0, missing: dict[str, int] = <factory>, rows_before_load: int | None = None, rows_after_load: int | None = None, checksum_before: str | None = None, checksum_after: str | None = None) -> None`
  TableQuality(name: str, source: str, rows_in: int = 0, rows_repaired: int = 0, repairs: list[str] = <factory>, duplicates_dropped: int = 0, rejected_by_reason: collections.Counter = <factory>, rows_rejected: int = 0, rows_valid: int = 0, missing: dict[str, int] = <factory>, rows_before_load: int | None = None, rows_after_load: int | None = None, checksum_before: str | None = None, checksum_after: str | None = None)
- **`missing_counts`** `def missing_counts(df: pandas.DataFrame) -> dict[str, int]`
- **`rerun_result`** `def rerun_result(t: src.data_pipeline.quality.TableQuality) -> str`
