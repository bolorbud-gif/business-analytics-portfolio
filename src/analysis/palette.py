"""The portfolio's colours, shared by the report charts (charts.py) and the dashboard.

Kept apart from charts.py so the dashboard can use them without loading Matplotlib and Seaborn.
Blue, orange and aqua are validated as distinguishable for colour-blind readers in every pair;
they are used in this fixed order, never more than three series in one chart.
"""

SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, NEUTRAL = "#e1e0d9", "#c3c2b7", "#f0efec"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
SERIES = [BLUE, ORANGE, AQUA]
