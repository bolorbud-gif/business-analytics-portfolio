# API Reference

Generated from the docstrings by `scripts/build_api_reference.py`; do not edit by hand.
Every function below is importable, e.g. `from src.analysis import statistical as st`.

## `src.analysis`

Exploratory data analysis package for the rare-earth / wind-power database.

### `src.analysis.exploratory`

Exploratory analysis: open the Assignment 4 database, check its quality, describe the data.

- **`analysis_sample`** `def analysis_sample(panel: pandas.DataFrame, include_non_buyers: bool = False) -> pandas.DataFrame`
  Country-years usable for the multivariate analysis: imports, wind capacity and total generation all recorded and positive (so logs exist). Adds a size tercile.
- **`balanced_panel`** `def balanced_panel(df: pandas.DataFrame, entity: str = 'country', period: str = 'year') -> pandas.DataFrame`
  Only the entities observed in every period that df covers (a balanced panel).
- **`buyer_price_changes`** `def buyer_price_changes(trade: pandas.DataFrame, start: int, end: int, trade_flow: str = 'Export') -> pandas.DataFrame`
  Each partner's volume and price (USD per kg) in both years, for partners present in both.
- **`buyer_volumes`** `def buyer_volumes(trade: pandas.DataFrame, year: int, trade_flow: str = 'Export') -> pandas.Series`
  Total kg per partner for one year and direction (Export = what each country bought).
- **`check_database`** `def check_database(con) -> pandas.DataFrame`
  Run data-quality checks on the database. One row per check: check, passed, detail.
- **`concentration`** `def concentration(values: pandas.Series) -> dict`
  Market concentration of a set of values (e.g. kg bought per country).
- **`coverage_by_year`** `def coverage_by_year(con) -> pandas.DataFrame`
  Number of trade rows per year and direction: shows which years each direction covers.
- **`describe_numeric`** `def describe_numeric(df: pandas.DataFrame, columns: list[str]) -> pandas.DataFrame`
  Univariate summary: count, missing, centre, spread and skew for each column.
- **`growth_vs_wind`** `def growth_vs_wind(panel: pandas.DataFrame, year: int) -> pandas.DataFrame`
  Country rows for one year with both import growth and wind generation change recorded.
- **`import_year_pattern`** `def import_year_pattern(panel: pandas.DataFrame, start: int, end: int, value: str = 'imports_from_china_kg', entity: str = 'partner') -> pandas.DataFrame`
  Which partners bought from China in both years, in only one, or in neither.
- **`load_country_panel`** `def load_country_panel(con) -> pandas.DataFrame`
  One row per partner country and year: imports from China, growth, wind, and size.
- **`load_trade`** `def load_trade(con) -> pandas.DataFrame`
  Every trade row with the partner's power mix (view partner_trade_energy).
- **`load_wind`** `def load_wind(con) -> pandas.DataFrame`
  Wind generation and capacity per country and year.
- **`market_shares`** `def market_shares(df: pandas.DataFrame, by: str, value: str, top: int = 10) -> pandas.DataFrame`
  Each group's share of the total, largest first; groups after `top` folded into one row.
- **`missing_by_year`** `def missing_by_year(df: pandas.DataFrame, columns: list[str], year: str = 'year') -> pandas.DataFrame`
  Percentage of missing values in each column, per year.
- **`open_database`** `def open_database(path=None)`
  Open the database with foreign keys ON. Returns (connection, path).
- **`period_change`** `def period_change(yearly: pandas.DataFrame, trade_flow: str, start: int, end: int) -> pandas.Series`
  Percent change in quantity, value and unit value between two years for one direction.
- **`price_mix_decomposition`** `def price_mix_decomposition(trade: pandas.DataFrame, start: int, end: int, trade_flow: str = 'Export', exclude: list[str] | None = None) -> dict`
  Split the change in the average price per kg into a price effect and a mix effect.
- **`table_row_counts`** `def table_row_counts(con) -> pandas.Series`
  Number of rows in each stored table.
- **`wind_trend`** `def wind_trend(wind: pandas.DataFrame, focus: str = 'China') -> tuple[pandas.DataFrame, dict]`
  Total wind capacity per year: the `focus` country vs all other countries combined.
- **`yearly_trade`** `def yearly_trade(trade: pandas.DataFrame) -> pandas.DataFrame`
  Totals per year and direction, with the average unit value (total value / total kg).

### `src.analysis.statistical`

Statistical analysis: correlation, partial correlation, regression, hypothesis tests.

- **`bootstrap_ci`** `def bootstrap_ci(values, statistic, n_boot: int = 2000, level: float = 0.95, seed: int = 0) -> dict`
  Percentile bootstrap confidence interval for any statistic of a 1-D sample.
- **`coefficient_evidence`** `def coefficient_evidence(result, term: str, factor: float = 10.0) -> dict`
  One coefficient of a log-log model, as evidence for a hypothesis.
- **`compare_groups`** `def compare_groups(df: pandas.DataFrame, value: str, group: str, order: list | None = None) -> dict`
  Kruskal-Wallis test: do the groups' distributions differ? (no normality assumed)
- **`compare_models`** `def compare_models(models: dict, terms: list[str]) -> pandas.DataFrame`
  The same coefficients across several fitted models, one row per model and term.
- **`correlation`** `def correlation(df: pandas.DataFrame, x: str, y: str, method: str = 'spearman') -> dict`
  Correlation between two columns over rows where both are present.
- **`correlation_matrix`** `def correlation_matrix(df: pandas.DataFrame, columns: list[str], method: str = 'spearman', log: bool = False) -> pandas.DataFrame`
  Pairwise correlation matrix of the columns (Spearman by default).
- **`correlation_table`** `def correlation_table(df: pandas.DataFrame, pairs: list[tuple[str, str]], method: str = 'spearman') -> pandas.DataFrame`
  correlation() for several column pairs, one row each.
- **`descriptive_table`** `def descriptive_table(df: pandas.DataFrame, columns: list[str], log_columns: list[str] = (), labels: dict | None = None, alpha: float = 0.05) -> pandas.DataFrame`
  Descriptive statistics of a model's variables (the usual "Table 1").
- **`fit_log_change_ols`** `def fit_log_change_ols(df: pandas.DataFrame, y: str, xs: list[str], entity: str, period: str, start, end, cov_type: str = 'HC1')`
  OLS in changes: log(y_end / y_start) on log(x_end / x_start), one row per entity.
- **`fit_log_ols`** `def fit_log_ols(df: pandas.DataFrame, y: str, xs: list[str], year_effects: bool = True, cluster: str | None = 'partner')`
  OLS of log10(y) on log10(xs), with optional year fixed effects.
- **`fit_ppml`** `def fit_ppml(df: pandas.DataFrame, y: str, xs: list[str], year_effects: bool = True, cluster: str | None = 'partner')`
  Poisson pseudo-maximum likelihood (PPML), the standard regression for trade flows.
- **`fold_change`** `def fold_change(elasticity: float, factor: float = 10.0) -> float`
  Business reading of an elasticity: y is multiplied by this when x is multiplied by `factor`. An elasticity of 0.94 means 10x the wind capacity goes with 8.7x the imports.
- **`group_assumptions`** `def group_assumptions(df: pandas.DataFrame, value: str, group: str, order: list | None = None, log: bool = False, alpha: float = 0.05) -> pandas.DataFrame`
  Assumption checks for comparing groups: Shapiro-Wilk in each group, Levene across them.
- **`growth_summary`** `def growth_summary(growth_pct: pandas.Series, extreme: float = 500.0) -> dict`
  Summary of percentage growth rates. Rates from tiny bases explode, so the median and interquartile range are reported instead of the mean.
- **`hypothesis_table`** `def hypothesis_table(tests: list[dict], alpha: float = 0.05) -> pandas.DataFrame`
  Collect hypothesis tests and adjust for testing several at once (Holm method).
- **`log10_positive`** `def log10_positive(s: pandas.Series) -> pandas.Series`
  log10 of the positive values; zero or negative becomes NaN (log is undefined).
- **`log_changes`** `def log_changes(df: pandas.DataFrame, columns: list[str], entity: str, period: str, start, end) -> pandas.DataFrame`
  Each entity's change from `start` to `end`, for entities with positive values of every column in both periods.
- **`log_ratio_to_pct`** `def log_ratio_to_pct(v: float) -> float`
  A natural-log ratio as a percent change: log(0.5) -> -50.0.
- **`normality_test`** `def normality_test(values: pandas.Series, log: bool = False, alpha: float = 0.05) -> dict`
  Shapiro-Wilk test of normality (on log10 values if log=True). Low p = not normal.
- **`paired_change`** `def paired_change(df: pandas.DataFrame, entity: str, period: str, value: str, start, end, test: str = 'wilcoxon') -> dict`
  Paired test of the change in `value` for entities seen in both periods.
- **`paired_log_ratios`** `def paired_log_ratios(df: pandas.DataFrame, entity: str, period: str, value: str, start, end) -> pandas.Series`
  log(end / start) of `value` for each entity seen, with a positive value, in both periods.
- **`partial_correlation`** `def partial_correlation(df: pandas.DataFrame, x: str, y: str, controls: list[str], log: bool = True, method: str = 'pearson') -> dict`
  Correlation of x and y after removing what the controls explain.
- **`regression_diagnostics`** `def regression_diagnostics(result) -> pandas.DataFrame`
  Assumption checks for an OLS result: unequal variance, residual normality, collinearity.
- **`residualize`** `def residualize(df: pandas.DataFrame, column: str, controls: list[str]) -> pandas.Series`
  What is left of `column` after a linear fit on the controls (with intercept).
- **`size_adjusted_residuals`** `def size_adjusted_residuals(df: pandas.DataFrame, x: str, y: str, controls: list[str], log: bool = True) -> pandas.DataFrame`
  Residuals of x and y after removing the controls (log10 first if log=True).
- **`split_medians`** `def split_medians(df: pandas.DataFrame, value: str, by: str) -> dict`
  Business reading of a correlation: the median of `value` where `by` is above its median, versus where it is at or below it.
- **`strength`** `def strength(r: float) -> str`
  Plain-language size of a correlation coefficient.
- **`tidy_coefficients`** `def tidy_coefficients(result) -> pandas.DataFrame`
  Coefficient table: estimate, standard error, p-value and 95% interval.
- **`top_share`** `def top_share(values, k: int = 5) -> float`
  Share of the total held by the k largest values.
- **`within_share`** `def within_share(df: pandas.DataFrame, column: str, entity: str = 'country', log: bool = True) -> float`
  Share of a variable's variance that is within entities (over time), not between them.

### `src.analysis.charts`

Charts for the exploratory analysis (Matplotlib + Seaborn).

- **`apply_style`** `def apply_style() -> None`
  Seaborn theme with the project's colours and recessive grid (applies to Matplotlib too).
- **`change_bars`** `def change_bars(changes: pandas.Series, title: str, subtitle: str, source: str, xlabel: str = 'Measure')`
  Percent changes as bars: blue up, red down, from a zero baseline.
- **`coefficient_plot`** `def coefficient_plot(models: dict[str, pandas.DataFrame], terms: dict[str, str], title: str, subtitle: str, source: str, xlabel: str = 'Elasticity (95% CI)', ylabel: str = 'Predictor')`
  Estimates with 95% intervals for selected terms, one colour per model.
- **`confounding_scatter`** `def confounding_scatter(raw: pandas.DataFrame, x: str, y: str, group: str, group_order: list[str], partial: pandas.DataFrame, raw_title: str, partial_title: str, title: str, subtitle: str, source: str, xlabel: str, ylabel: str)`
  Two panels: the raw log-log relationship coloured by a size group, then the same relationship after removing size (residuals).
- **`correlation_heatmap`** `def correlation_heatmap(matrix: pandas.DataFrame, labels: list[str], title: str, subtitle: str, source: str)`
  Correlation matrix (lower triangle) on a blue (positive) / gray (zero) / red scale.
- **`cv_comparison`** `def cv_comparison(panels: dict, title: str, subtitle: str, source: str, chosen: dict | None = None)`
  Cross-validated score of each model, mean +- one standard deviation across folds.
- **`group_strip`** `def group_strip(df: pandas.DataFrame, value: str, group: str, order: list[str], ylabel: str, title: str, subtitle: str, source: str, tick_labels: list[str] | None = None, xlabel: str = '')`
  Every observation per group on a log scale, with the median marked.
- **`line_trend`** `def line_trend(df: pandas.DataFrame, x: str, series: list[str], labels: list[str], ylabel: str, title: str, subtitle: str, source: str, xlabel: str = 'Year')`
  Up to three lines on one axis, each labelled at its end and in the legend.
- **`log_histogram`** `def log_histogram(values: pandas.Series, xlabel: str, title: str, subtitle: str, source: str, bins: int = 20)`
  Histogram with log-spaced bins, for right-skewed positive values.
- **`market_share_bars`** `def market_share_bars(shares: pandas.DataFrame, title: str, subtitle: str, source: str, ylabel: str = 'Buying country')`
  Horizontal bars of each country's share (output of exploratory.market_shares).
- **`pair_plot`** `def pair_plot(df: pandas.DataFrame, columns: list[str], labels: list[str], hue: str, hue_order: list[str], title: str, subtitle: str, source: str, height: float = 2.1)`
  Seaborn pair plot of log10 values: every pairwise relationship at once, coloured by group.
- **`predicted_vs_actual`** `def predicted_vs_actual(actual, predicted, labels, title: str, subtitle: str, source: str, note: str | None = None, n_labels: int = 3, xlabel: str = 'Actual imports from China (kg, log scale)', ylabel: str = 'Predicted imports (kg, log scale)')`
  Predicted against actual values on log axes, with the perfect-prediction line and dotted lines where a prediction is 10 times too high or too low. The n_labels largest misses are labelled (labels: one name per point).
- **`relationship_scatter`** `def relationship_scatter(df: pandas.DataFrame, x: str, y: str, xlabel: str, ylabel: str, title: str, subtitle: str, source: str, note: str | None = None, xscale: str = 'linear', yscale: str = 'linear', linthresh: float = 0.1, ref_x: float | None = None, ref_y: float | None = None, note_loc: str = 'upper left')`
  Scatter of one relationship, to show what a reported correlation looks like.
- **`roc_chart`** `def roc_chart(curves: dict, title: str, subtitle: str, source: str, marker: tuple | None = None)`
  ROC curves (true-positive rate against false-positive rate), each labelled with its AUC, against the diagonal of a model that guesses (AUC 0.5).
- **`save`** `def save(fig, name: str, folder: pathlib.Path = WindowsPath('C:/Users/mcobp/business-analytics-portfolio/docs/figures')) -> pathlib.Path`
  Save a figure as 300 dpi PNG and vector SVG in docs/figures/ (or `folder`).
- **`show`** `def show(fig, name: str | None = None, save_figure: bool = True, folder: pathlib.Path = WindowsPath('C:/Users/mcobp/business-analytics-portfolio/docs/figures'))`
  Display a figure in a notebook, save it with save() if asked, then close it.

## `src.modeling`

Analytics engine (Assignment 6): predict a country's imports of Chinese rare-earth compounds, and whether it is a major buyer, from its power sector.

### `src.modeling.train`

Train the analytics engine: data, pipelines, split, tuning, final evaluation, saving.

- **`build_pipeline`** `def build_pipeline(estimator, config: dict) -> sklearn.pipeline.Pipeline`
  Preprocessing and model in one object, so every fit (in CV, tuning or final training) learns the medians and scales from the training rows alone.
- **`build_preprocessor`** `def build_preprocessor(config: dict) -> sklearn.compose._column_transformer.ColumnTransformer`
  Preprocessing that is fitted on training rows only, because it sits in the pipeline.
- **`candidates`** `def candidates(task: str, config: dict) -> dict`
  The models to compare, each as (pipeline, hyperparameter grid). The first is always the dummy baseline, which ignores the features.
- **`data_fingerprint`** `def data_fingerprint(data: pandas.DataFrame, columns: list[str]) -> str`
  SHA-256 of the training rows (the given columns, in order): the same data always gives the same fingerprint, so a saved model can be traced to the exact data behind it.
- **`feature_columns`** `def feature_columns(config: dict) -> list[str]`
  Every feature the models use, size features first.
- **`final_model`** `def final_model(task: str, name: str, params: dict, data: pandas.DataFrame, config: dict)`
  Refit the chosen pipeline, with its tuned hyperparameters, on all the data.
- **`finish_task`** `def finish_task(task: str, selection: dict, tested: dict, data: pandas.DataFrame, config: dict) -> dict`
  Combine one task's model selection and test results with its final pipeline, refitted on all the data with the tuned hyperparameters.
- **`fit_and_test`** `def fit_and_test(task: str, name: str, train: pandas.DataFrame, test: pandas.DataFrame, config: dict, group: str = 'country') -> dict`
  Tune the chosen candidate on the whole training set, then score it once on the test set. The dummy baseline is scored on the same test set for comparison. For classification the probability threshold is also chosen on the training set: the one with the lowest expected business cost (config costs).
- **`git_state`** `def git_state(root: pathlib.Path = WindowsPath('C:/Users/mcobp/business-analytics-portfolio')) -> dict`
  The code version: current git commit and whether there were uncommitted changes (None if git isn't available).
- **`load_config`** `def load_config(path: pathlib.Path = WindowsPath('C:/Users/mcobp/business-analytics-portfolio/config/model_params.yaml')) -> dict`
  Read the engine's settings (features, target, split, tuning grids, output path).
- **`load_dataset`** `def load_dataset(con, config: dict, lag: int | None = None) -> pandas.DataFrame`
  The modeling data: the Assignment 5 analysis sample (country-years with imports, wind capacity and total generation all positive), with the two targets added.
- **`load_features`** `def load_features(con, years: list[int], lag: int = 0) -> pandas.DataFrame`
  One row per partner country and year with power data: the engine's features, the actual imports from China (NaN = none recorded) and the trade value.
- **`main`** `def main(argv=None) -> int`
  Command line: train, evaluate and save the engine.
- **`model_bundle`** `def model_bundle(engine: dict, config: dict, source: str) -> dict`
  What gets saved: both final pipelines (preprocessing included) plus what's needed to use and audit them: problem types, features, target, threshold, business costs, scores and provenance.
- **`provenance`** `def provenance(data: pandas.DataFrame, config: dict, source: str) -> dict`
  Where a saved model came from: data (source, size, years, fingerprint), code (git commit), settings (a full copy of the config, random_state) and environment.
- **`safe_log10`** `def safe_log10(X)`
  log10 with a floor of LOG_FLOOR, so a zero (no solar, no wind) stays finite.
- **`save_bundle`** `def save_bundle(bundle: dict, path: pathlib.Path) -> pathlib.Path`
  Save the bundle with joblib (models/ is git-ignored: the models encode restricted data).
- **`select_model`** `def select_model(task: str, train: pandas.DataFrame, config: dict, group: str = 'country') -> dict`
  Nested cross-validation of every candidate on the training set; the best one wins.
- **`split_by_country`** `def split_by_country(df: pandas.DataFrame, config: dict, label: str = 'major_buyer', group: str = 'country') -> tuple[pandas.DataFrame, pandas.DataFrame]`
  Hold out whole countries as the test set, stratified on the major-buyer label.
- **`synthetic_dataset`** `def synthetic_dataset(config: dict, n_countries: int = 60, seed: int = 751) -> pandas.DataFrame`
  Random data with the same columns as load_dataset, for running the notebook and the tests without the restricted data. The numbers are fake.
- **`targets`** `def targets(config: dict) -> dict`
  The column each task predicts.
- **`train_engine`** `def train_engine(data: pandas.DataFrame, config: dict) -> dict`
  Run the whole workflow for both tasks on a dataset from load_dataset (or synthetic_dataset) and return everything needed to report and save it: data, split, cross-validation, test scores and the final pipelines.

### `src.modeling.evaluate`

Evaluation for the analytics engine: metrics, cross-validation and leakage checks.

- **`best_threshold`** `def best_threshold(y_true, y_score, costs: dict | None = None) -> float`
  The threshold (0.05 to 0.95) with the lowest expected cost, or the best F1 if no costs are given. On a tie, the one closest to 0.5.
- **`bootstrap_ci`** `def bootstrap_ci(y_true, y_hat, groups, task: str, metric: str, n_boot: int = 1000, random_state: int = 42, threshold: float = 0.5, costs: dict | None = None) -> dict`
  95% interval for a test-set metric, resampling whole countries (with replacement).
- **`choose_threshold`** `def choose_threshold(model, X, y, groups, cv, costs: dict | None = None) -> float`
  The probability threshold with the lowest business cost (or best F1 without costs), chosen on training data only.
- **`classic_leak_vs_pipeline`** `def classic_leak_vs_pipeline(pipeline, X, y, groups, task: str, n_splits: int = 5) -> pandas.DataFrame`
  Three ways to score the same pipeline, from most to least leaky.
- **`classification_metrics`** `def classification_metrics(y_true, y_score, threshold: float = 0.5, costs: dict | None = None) -> dict`
  Precision, recall, F1, accuracy and ROC AUC for predicted probabilities, plus the expected business cost per country when `costs` are given.
- **`confusion_table`** `def confusion_table(y_true, y_score, threshold: float = 0.5, labels: tuple = ('Smaller buyer', 'Major buyer')) -> pandas.DataFrame`
  Counts of right and wrong calls at a threshold: rows are the truth, columns the call.
- **`cv_scores`** `def cv_scores(pipeline, X, y, groups, cv, task: str) -> pandas.DataFrame`
  Fit a fresh copy of the pipeline on each training fold and score it on the held-out fold. One row per fold; preprocessing is refitted inside every fold.
- **`expected_cost`** `def expected_cost(y_true, y_score, threshold: float, costs: dict) -> float`
  Average business cost per country of the calls made at `threshold`.
- **`feature_availability`** `def feature_availability(features: pandas.DataFrame, config: dict) -> pandas.DataFrame`
  Is every feature available when the engine is used? One row per feature.
- **`group_folds`** `def group_folds(task: str, n_splits: int = 5, random_state: int = 42)`
  Folds that keep each country in one fold. Classification folds are also stratified, so every fold has both classes.
- **`leakage_screen`** `def leakage_screen(df: pandas.DataFrame, columns: list[str], target: str, forbidden: list[str], threshold: float = 0.9) -> pandas.DataFrame`
  Flag candidate features that could leak the target.
- **`nested_cv`** `def nested_cv(pipeline, grid: dict, X, y, groups, task: str, n_splits: int = 5, random_state: int = 42, costs: dict | None = None) -> pandas.DataFrame`
  Honest performance of a *tuned* model: tuning runs inside each outer training fold.
- **`operating_point`** `def operating_point(y_true, y_score, threshold: float) -> dict`
  Where a threshold sits on the ROC curve: its false- and true-positive rates.
- **`out_of_fold_scores`** `def out_of_fold_scores(model, X, y, groups, cv) -> numpy.ndarray`
  Probability of the positive class for every training row, each predicted by a copy of the model fitted without that row's country (a tuned search's best model is used).
- **`random_vs_group_cv`** `def random_vs_group_cv(pipeline, X, y, groups, task: str = 'regression', n_splits: int = 5, random_state: int = 42) -> pandas.DataFrame`
  Group leakage: random folds put the same country in training and test.
- **`regression_metrics`** `def regression_metrics(y_true, y_pred) -> dict`
  MAE, RMSE and R-squared of predictions on the log10 scale.
- **`roc_points`** `def roc_points(y_true, y_score) -> dict`
  False- and true-positive rates for an ROC curve, plus its AUC.
- **`score`** `def score(model, X, y, task: str, threshold: float = 0.5, costs: dict | None = None) -> dict`
  The task's metrics for a fitted model on (X, y); classification uses `threshold` and reports the expected cost per country when `costs` are given.
- **`split_comparison`** `def split_comparison(datasets: dict, pipeline, features: list[str], target: str, task: str, train_years: list[int], test_years: list[int], n_splits: int = 5, random_state: int = 42, group: str = 'country') -> pandas.DataFrame`
  The same pipeline scored two ways on each dataset: cross-validated by country, and time-aware (train on earlier years, test on later ones).
- **`summarize_cv`** `def summarize_cv(results: dict, task: str) -> pandas.DataFrame`
  One row per model: the mean and standard deviation of each metric over the folds, and whether the model beats the baseline (the first model) on the main metric.
- **`threshold_table`** `def threshold_table(y_true, y_score, thresholds=(0.3, 0.4, 0.5, 0.6, 0.7), costs: dict | None = None) -> pandas.DataFrame`
  Precision, recall, F1 (and expected cost, if `costs` are given) at several thresholds.
- **`tune`** `def tune(pipeline, grid: dict, X, y, groups, cv, scoring: str)`
  Grid search over the pipeline's hyperparameters, with folds split by country.

### `src.modeling.predict`

Use the saved analytics engine: load it, check it, predict.

- **`expected_vs_actual`** `def expected_vs_actual(bundle: dict, features: pandas.DataFrame) -> pandas.DataFrame`
  Expected and actual imports from China for each row of `features` (for example train.load_features(con, [2025], bundle["feature_lag_years"]): every country with power data, paired the way the engine was trained).
- **`load_engine`** `def load_engine(path=None) -> dict`
  Load a saved engine bundle and check it before use.
- **`main`** `def main(argv=None) -> int`
  Command line: expected vs actual imports for one year, with recommended actions.
- **`predict`** `def predict(bundle: dict, features: pandas.DataFrame) -> pandas.DataFrame`
  Predictions for each row of `features` (which needs every column in bundle["features"]; missing values are allowed and filled by the pipeline).
- **`recommend`** `def recommend(table: pandas.DataFrame, bundle: dict) -> pandas.DataFrame`
  Add a recommended action (and the reason) to an expected_vs_actual table.

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
