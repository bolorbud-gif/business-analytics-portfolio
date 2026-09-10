\# AI Tool Use



\## Tools used

\- ChatGpt for manual process. I will try Claude code for checking my works as well. 



\## Where I used it

\- \*\*Assignment 4 (ETL):\*\* Debugged the multi-format extract function. It found a

&#x20; dtype mismatch on the join key that I had missed. I wrote the transform logic.

\- \*\*Assignment 5 (EDA):\*\* Asked it to explain seaborn's FacetGrid API. Wrote the

&#x20; plots myself afterward.

\- \*\*Assignment 6 (Model):\*\* Generated the cross-validation boilerplate. I chose the

&#x20; model, the features, and the metrics.



\## Where I deliberately did not use it

\- Schema design. I wanted to work through normalization myself.

\- Interpretation of the regression results.



\## Something it got wrong

It suggested scaling features before the train/test split. I caught this because we

covered leakage on Day 3. Moved the scaler inside the pipeline.

