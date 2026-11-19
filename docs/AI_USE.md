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
- **Assignment 5 (Exploratory analysis):** Used Claude Code to write the analysis functions
  (`src/analysis/`), the two notebooks, the seven charts, the findings document and the
  executive summary from the Assignment 5 brief, working against my Assignment 4 database.

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

## Verification

- I checked Japan's 2024 import growth by hand (63.0%), ran the pipeline twice to confirm
  nothing changed, and reviewed the quality report. 43 automated tests cover the pipeline
  and the analysis functions.
- I compile all of my work in one folder and save its version history in Google Drive.
