# Executive Summary: Rare-Earth Demand and the Wind Build-Out

*Assignment 5 · Exploratory analysis of China's rare-earth compound trade (HS 284690) and national
wind power, 2020–2025. Full statistical report: [statistical_analysis_report.md](statistical_analysis_report.md).*

## The question

Wind turbines are a major new use of rare earths, and China dominates their supply. Does the global
wind build-out drive countries' purchases of Chinese rare earths, and how exposed are buyers?

## Key findings

1. **Five countries take 83% of China's rare-earth compound exports.** The United States (35.5%) and
   Japan (22.5%) alone take 58%. The market is highly concentrated, with an HHI of 2,054.

   ![Concentration](figures/01_concentration.png)

2. **The 2024 price fall was real, and largest for the biggest buyers.** China shipped 5.7% more by
   weight but earned 26.4% less, so the average price fell 30%, from $15.3 to $10.7 per kg. Holding each
   buyer's 2023 volume fixed, prices fell 35%: a genuine price fall, not a shift in who buys. It was
   concentrated in large buyers: Japan −62%, Korea −35%, the Netherlands −31%, the US −9%. For the
   typical, mostly small, buyer the change (−11%) is too uncertain to confirm.

3. **Wind capacity is growing fast, and China is building the most.** Capacity across 60 countries
   rose 75% from 2020 to 2025. China more than doubled its own (+127%) and now exceeds the other 59
   countries combined.

4. **Country size, not wind, best predicts who buys.** Countries with more wind do import more: 10×
   the wind capacity goes with about 9× the imports. But that's because large economies have more of
   both. At the same size, 10× the wind goes with only about 1.6× the imports, which can't be told
   apart from no effect (95% range 0.8× to 3.3×). Size dominates: 10× the size, about 55× the imports.
   Five formal hypothesis tests, with their assumptions checked and corrected for running several at
   once, support this picture.

   ![Size explains the wind link](figures/04_size_confound.png)

## Business implications

- **Concentration risk sits with a few buyers.** An export restriction or price change by China would
  hit the US, Japan and the Netherlands first. Their buyers should prioritise supplier diversification
  and stockpiles.
- **Benchmark prices against the big buyers' cuts.** Japan, Korea and the Netherlands paid 31–62% less
  per kg in 2024. Buyers who didn't see a cut should check, grade by grade, whether they are paying
  above the market.
- **Don't forecast rare-earth demand from wind targets alone.** Overall economic and industrial size
  predicts compound imports far better. Wind's own effect is uncertain, not proven to be zero. Wind's rare-earth demand probably arrives as finished
  **permanent magnets**, which this product code doesn't capture.
- **China's own wind boom may tighten supply.** Its domestic capacity more than doubled, so more of its
  rare-earth output may be used at home rather than exported. This is a hypothesis for the next stage.

## Recommendations for the next stage (modeling)

1. **Complete the data.** Obtain China's exports for every year 2020–2025; today only 2023–2024 exist,
   so growth can be measured for one year only.
2. **Add permanent magnets (HS 850511)** to test the wind link where it is most likely to appear.
3. **Model log quantities with size controls**, test robustness without the two largest buyers, and
   treat growth as a log ratio.

## Confidence and limits

The data passes all 19 quality checks. Every test's assumptions were checked (Shapiro-Wilk for
normality, Levene for equal variances, plus regression diagnostics), and where an assumption failed, a
test that doesn't need it was used. Every hypothesis was also re-tested as a log-log regression, with the
same verdicts. The size finding holds without the 16 small buyers that bought in only one of the two years,
and in a Poisson model (PPML) that counts their missing years as zero.

**Statistically significant isn't the same as important.** Two results aren't statistically significant
but are too large to dismiss: wind's effect at the same size, and the link between wind growth and
import growth (+50% median import growth where wind grew most, −11% elsewhere). They need more years of
data before anyone acts on them, or rules them out.

Findings describe **associations** in a short window (102 country-years). They aren't causal estimates,
and they cover rare-earth *compounds* only.
