"""Analytics engine (Assignment 6): predict a country's imports of Chinese rare-earth
compounds, and whether it is a major buyer, from its power sector.

- train.py: data, pipelines, country-level split, nested cross-validation, tuning, saving
- evaluate.py: metrics (MAE, RMSE, R2; precision, recall, F1, ROC AUC), cross-validation,
  threshold choice and leakage checks
- predict.py: load the saved engine, check it, and predict
"""

__all__ = ["evaluate", "predict", "train"]
