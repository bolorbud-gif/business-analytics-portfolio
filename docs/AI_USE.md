# AI Tool Use

*Last updated: 2026-11-19*

## Tools used

- Claude Code (Claude Pro subscription)
- ChatGPT (paid subscription)

## Where I used it

- **Assignment 3 (Proposal: "Does geographic remoteness increase local financial dependence? Evidence from Mongolia"):**
  Used AI to find related articles, identify independent- and dependent-variable
  methodologies and relevant theories, suggest synonyms, correct grammar, and format
  citations. All of the cited sources are ones I had already used before working with
  AI, which is why I could recognize and verify them. I also used it to compare
  different analysis equations. I developed the hypotheses, ordered the logic between
  the ideas, and wrote my own thoughts myself.
- **Proposal rewrite (rare-earth topic):** The portfolio moved to the rare-earth topic in
  Assignment 4, so after Assignment 6 I asked Claude Code to draft a rewrite of the proposal
  in the original proposal's structure, from the work in Assignments 4–6. It checked each
  journal article it cited against Crossref, and opened the news article and data pages. I
  then revised the draft myself in Word: I rewrote the introduction, extended the problem
  definition, added Depraiter & Goutte (2023), and shortened the methods and references. I
  chose the final title, "Does Wind Power Growth Drive Demand for Chinese Rare-Earth
  Exports?", so that it matches hypotheses H1–H5. Claude Code converted my Word file to
  `docs/proposal.pdf` and fixed two equations and three references I asked it to. The Mongolia
  proposal stays in the git history.
- **Portfolio repository setup:** Used Claude Code to check the required folder
  structure, rename the notebooks, update `.gitignore`, add the MIT license, and commit
  the proposal to GitHub.
- **Assignment 4 (Data pipeline, rare-earth trade and wind power):** Used Claude Code to
  build the ETL pipeline (Pandas, SQLAlchemy, SQLite), Pandera validation, the quality
  report and re-run check, the synthetic sample, the ERD, the data dictionary and the 3NF
  normalization. I chose the topic and data sources and specified the analysis tables:
  imports from China, the growth formula ((this year − previous year) ÷ previous year ×
  100), wind generation, change and capacity, the merge on country and year, and the
  one-sheet layout. I chose to measure imports as countries buying from China.
- **Assignment 5 (Exploratory analysis):** Used Claude Code to write the analysis package
  (`src/analysis/`), the two notebooks, the eleven Matplotlib/Seaborn charts, the hypothesis tests
  and regression diagnostics, the statistical analysis report, the API reference and the
  executive summary from the Assignment 5 brief, working against my Assignment 4 database.
  I asked which regressions the data supports, whether countries that skip years break log-log
  OLS or ARIMA, and for each hypothesis to be checked with log-log OLS and a descriptive Table 1;
  those answers were added as the regression check and robustness sections.
- **Assignment 6 (Analytics engine):** Used Claude Code to build `src/modeling/` (training, evaluation
  and prediction), the modeling notebook, three charts and the engine's tests, following the topics I
  gave it: baseline rule, dummy regressor, splitting, leakage and pipelines, MAE/RMSE/R²,
  cross-validation, tuning, saving the model, the engine's structure, and precision, recall, F1, ROC
  and AUC. The two targets (imports in kg, and major buyers at 10 tonnes a year) build on my
  Assignment 5 analysis. I then checked it against the course's analytics checklist, which led to
  last year's power data as features (available at prediction time), a threshold set by the cost of
  each error, provenance in the saved model, and recommended actions.
- **Assignment 7 (Dashboard):** Used Claude Code to build the Streamlit app (`src/dashboard/`), the
  results snapshot with its rebuild-and-compare check (`scripts/deploy.py`), the tests and
  `docs/deployment.md`, following the course's dashboard process and checklist. I decided to commit the
  country-level results snapshot (`data/published/`); the raw files stay out. The ninety-second test
  with someone who hasn't seen the project is mine to run.

## Where I deliberately did not use it

- The core ideas and arguments of the project. They come partly from my own previous
  research, so I did not use AI to generate them.

## Something it got wrong

- Even when my instructions were correct, it created duplicate folders and added files
  that were not required.
- It first stored trade values as REAL (floating point). I caught this with the course's
  common-mistakes checklist, and it was changed to exact integer dollars. It also suggested
  opening the database in a way that skipped foreign-key checks.
- In Assignment 5 it first gave a chart the title "China buys at higher prices than it sells",
  which the data can't support: the buying and selling rows come from different years. The title
  was corrected. One notebook cell also crashed on the synthetic sample (it assumed China was in
  the data) until it was fixed.
- It first summarised the 2024 data as "prices fell sharply" (the aggregate unit value fell 30%).
  Then it over-corrected: because a per-buyer test wasn't statistically significant, it concluded
  that most of the drop was a mix effect. I checked the analysis against the course's
  common-mistakes list (p-values without effect sizes, "significant" used to mean "important",
  assumptions never checked, correlations with no scatter plot). A fixed-basket price index then
  showed the opposite: at fixed volumes, prices fell 35%, so it was a real price fall, concentrated
  in the largest buyers. The report, summary and notebook were corrected. Every hypothesis now
  reports its business magnitude and effect size before the p-value, with Shapiro-Wilk and Levene
  checks, and every correlation has a scatter plot.

- In Assignment 6, its first saved model couldn't be loaded: run as `python -m`, the custom log step
  was saved as part of `__main__`. Running the prediction command exposed it; a test now checks it.
  Its first classifier also used a fixed 0.5 threshold, which made precision and recall swing between
  folds; the threshold is now chosen on training data.
- Its first engine used same-year power data, which aren't published until the year is over, so it
  couldn't forecast; the checklist's feature-availability item caught this. Its first action rules
  also called India "in line with expectations" while it bought 2% of the expected amount, and told
  the team to approach every country in 2025, a year with no trade data yet. Both rules were fixed and
  are now tested.

## Verification

- I checked Japan's 2024 import growth by hand (63.0%), ran the pipeline twice to confirm
  nothing changed, and reviewed the quality report. 147 automated tests cover the pipeline,
  the analysis functions, the analytics engine and every page of the dashboard.
- I compile all of my work in one folder and save its version history in Google Drive.
