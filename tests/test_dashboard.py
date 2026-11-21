"""Tests for the dashboard (src/dashboard): the results snapshot and every page of the app.

They run on the committed snapshot and on a snapshot built from the committed synthetic sample,
so no restricted data is needed.
"""

import copy
import json
import os
import re
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

from src.analysis import charts
from src.dashboard import components as ui
from src.dashboard import data
from src.modeling import train as tr

APP = data.ROOT / "src" / "dashboard" / "app.py"
PAGES = ["answer_page", "wind_page", "actions_page", "market_page", "engine_page", "data_page", "limits_page"]
TABLES = set(data.TABLES)


def page_test(page: str, snapshot=data.PUBLISHED) -> AppTest:
    """Run one page of the app headlessly, on a given snapshot, guarded as the app's navigation runs it."""
    script = (f"import runpy\nns = runpy.run_path(r'{APP}', run_name='dashboard_test')\n"
              f"ns['guarded'](ns['{page}'])()\n")
    os.environ["DASHBOARD_DATA"] = str(snapshot)
    try:
        return AppTest.from_string(script, default_timeout=120).run()
    finally:
        os.environ.pop("DASHBOARD_DATA", None)


@pytest.fixture(scope="module")
def sample_snapshot(tmp_path_factory):
    """A snapshot built from the committed synthetic sample, with small tuning grids (fast)."""
    from src.analysis import exploratory as ex
    from src.data_pipeline.pipeline import run_pipeline
    tmp = tmp_path_factory.mktemp("dash")
    run_pipeline(data.ROOT / "data" / "sample", {"trade": "data1.xlsx", "electricity": "data2.xlsx"},
                 f"sqlite:///{tmp / 'sample.db'}", rejected_dir=tmp / "rejected")
    config = copy.deepcopy(tr.load_config())
    config["split"]["cv_folds"] = 3
    config["tuning"] = {"regression": {"ridge": {"model__alpha": [1.0]},
                                       "random_forest": {"model__max_depth": [3], "model__min_samples_leaf": [3]}},
                        "classification": {"logistic": {"model__C": [1.0]},
                                           "random_forest": {"model__max_depth": [3],
                                                             "model__min_samples_leaf": [3]}}}
    con, _ = ex.open_database(tmp / "sample.db")
    engine = data.train_engine_artifact(con, real=False, path=tmp / "engine.joblib", config=config)
    snapshot = data.build_snapshot(con, data.load_engine_artifact(engine), real=False, source="sample.db")
    con.close()
    return data.save_snapshot(snapshot, tmp / "snapshot")


# --- The committed snapshot -----------------------------------------------------------------------

def test_committed_snapshot_has_exactly_the_expected_files():
    snap = data.load_snapshot(data.PUBLISHED)
    assert set(snap["tables"]) == TABLES  # nothing else (e.g. raw extracts) slipped in
    assert snap["meta"]["source"] == "real"
    assert len(snap["meta"]["data_sha256"]) == 64
    files = {f.name for f in data.PUBLISHED.iterdir()}
    assert files == {f"{t}.csv" for t in TABLES} | {"summary.json", "meta.json"}


def test_committed_snapshot_matches_the_reported_results():
    """Headline numbers the report, the README and the dashboard all quote."""
    s = data.load_snapshot(data.PUBLISHED)
    a = s["summary"]["analysis"]
    assert a["sample"]["rows"] == 102 and a["sample"]["countries"] == 58
    assert round(a["concentration_latest"]["top5_share"], 2) == 0.83
    assert round(a["price_decomposition"]["price_effect_pct"]) == -35
    assert round(a["model_b"]["wind"], 2) == 0.20 and round(a["model_b"]["size"], 2) == 1.74
    assert a["checks_passed"] == a["checks_total"] == 19
    h = s["tables"]["hypotheses"].set_index("hypothesis")["result"]
    assert list(h) == ["Supported", "Not supported", "Not supported", "Not supported", "Supported"]


# --- Building, saving, comparing --------------------------------------------------------------------

def test_sample_snapshot_has_every_table_and_compares_equal_to_itself(sample_snapshot):
    snap = data.load_snapshot(sample_snapshot)
    assert set(snap["tables"]) == TABLES
    assert snap["meta"]["source"] == "synthetic"
    assert data.compare_snapshots(sample_snapshot, sample_snapshot) == []


def test_compare_snapshots_finds_a_changed_number(sample_snapshot, tmp_path):
    import shutil
    other = tmp_path / "other"
    shutil.copytree(sample_snapshot, other)
    table = (other / "country_year.csv").read_text(encoding="utf-8").splitlines()
    header, first = table[0].split(","), table[1].split(",")
    col = header.index("imports_from_china_kg")
    first[col] = str(float(first[col]) * 2)
    table[1] = ",".join(first)
    (other / "country_year.csv").write_text("\n".join(table) + "\n", encoding="utf-8")
    problems = data.compare_snapshots(sample_snapshot, other)
    assert any(p.startswith("country_year.imports_from_china_kg") for p in problems)


def test_compare_snapshots_ignores_build_time_and_commit(sample_snapshot, tmp_path):
    import json
    import shutil
    other = tmp_path / "other"
    shutil.copytree(sample_snapshot, other)
    meta = json.loads((other / "meta.json").read_text(encoding="utf-8"))
    meta.update(created_utc="2000-01-01T00:00:00+00:00", git_commit="abc", uncommitted_changes=False)
    (other / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert data.compare_snapshots(sample_snapshot, other) == []


def test_load_snapshot_explains_a_missing_folder(tmp_path):
    with pytest.raises(data.SnapshotError, match="deploy.py build --sample"):
        data.load_snapshot(tmp_path / "missing")


def test_load_snapshot_names_missing_and_unreadable_files(tmp_path):
    import shutil
    broken = tmp_path / "broken"
    shutil.copytree(data.PUBLISHED, broken)
    (broken / "actions.csv").unlink()
    with pytest.raises(data.SnapshotError, match="incomplete .*actions"):
        data.load_snapshot(broken)
    shutil.copy(data.PUBLISHED / "actions.csv", broken / "actions.csv")
    (broken / "summary.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(data.SnapshotError, match="can't be read"):
        data.load_snapshot(broken)


def test_engine_artifact_carries_its_evaluation_evidence(sample_snapshot):
    snap = data.load_snapshot(sample_snapshot)
    assert {"regression", "classification"} == set(snap["tables"]["engine_cv"]["task"])
    assert len(snap["tables"]["engine_test"]) == 4  # model and baseline, two tasks
    artifact = snap["summary"]["engine"]["artifact"]
    assert len(artifact["data_sha256"]) == 64 and artifact["random_state"] == 42


def test_load_engine_artifact_rejects_an_outdated_bundle(tmp_path):
    import joblib
    old = {"regressor": None, "classifier": None, "features": [], "target": {}, "threshold": 0.5,
           "versions": {"scikit-learn": __import__("sklearn").__version__}}
    joblib.dump(old, tmp_path / "old.joblib")
    with pytest.raises(data.SnapshotError, match="Retrain"):
        data.load_engine_artifact(tmp_path / "old.joblib")


# --- The app ------------------------------------------------------------------------------------------

def test_dashboard_reuses_the_palette_without_loading_the_heavy_packages():
    source = (data.ROOT / "src" / "dashboard" / "components.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{6}", source)  # colours come from src.analysis.palette, not a copy
    assert (ui.BLUE, ui.ORANGE, ui.MUTED, ui.SERIES) == (charts.BLUE, charts.ORANGE, charts.MUTED, charts.SERIES)
    code = ("import sys; import src.dashboard.components, src.dashboard.data, src.modeling.evaluate; "
            "print([m for m in ('matplotlib', 'seaborn', 'statsmodels', 'pandera') if m in sys.modules])")
    out = subprocess.run([sys.executable, "-c", code], cwd=data.ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"  # so the app starts fast


def test_charts_must_have_a_title():
    with pytest.raises(ValueError, match="title"):
        ui.show(ui.threshold_lines(__import__("pandas").DataFrame(
            {"threshold": [0.5], "precision": [1.0], "recall": [1.0], "F1": [1.0]}), 0.5), "")


def test_formatting_helpers():
    assert ui.fmt_kg(850) == "850 kg" and ui.fmt_kg(12_300) == "12.3 t" and ui.fmt_kg(4_965_680) == "4,966 t"
    assert ui.fmt_pct(-34.8, signed=True) == "-35%"
    assert ui.fold(0.2) == "1.6x" and ui.fold(1.742) == "55x"


def test_app_opens_on_the_answer_with_the_one_conclusion():
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not at.exception and not at.error
    assert at.title[0].value == "Does wind power growth drive demand for Chinese rare-earth exports?"
    text = " ".join(m.value for m in at.markdown)
    assert "Country size, not wind, drives demand" in text
    assert "The decision it supports" in text
    assert [m.label for m in at.metric] == ["Imports for 10x wind (same size)", "Imports for 10x size (same wind)",
                                            "Top-5 buyers' share (2024)", "Major-buyer ranking (AUC)"]
    assert [m.value for m in at.metric][:2] == ["1.6x", "55x"]
    assert any("results built" in c.value for c in at.sidebar.caption)  # freshness, app-wide


FILTERED = {"wind_page", "actions_page", "market_page", "engine_page", "data_page"}


@pytest.mark.parametrize("page", PAGES)
def test_every_page_runs_on_the_committed_snapshot_with_its_notes(page):
    at = page_test(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert at.title
    assert at.caption[0].value.startswith("🕒 Data as of: China's trade records")  # freshness under the title
    if page != "limits_page":  # every evidence page ends with sample, uncertainty, provenance, limitations
        notes = " ".join(m.value for m in at.markdown)
        for part in ("**Sample:**", "**Uncertainty:**", "**Provenance:**", "**Limitations:**"):
            assert part in notes, (page, part)
    charts = at.get("vega_lite_chart")
    assert charts or page in {"data_page", "limits_page"}, page
    for chart in charts:  # every chart has a title
        assert json.loads(chart.proto.spec)["title"]["text"], page
    widgets = [w for kind in ("multiselect", "selectbox", "slider", "select_slider", "text_input", "toggle")
               for w in getattr(at.main, kind)]
    assert not widgets, (page, "filters belong in the sidebar")
    assert bool(at.sidebar.header) == (page in FILTERED)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_runs_on_a_synthetic_snapshot_and_says_so(page, sample_snapshot):
    at = page_test(page, sample_snapshot)
    assert not at.exception, [e.value for e in at.exception]
    assert any("Synthetic data" in w.value for w in at.warning)


def test_missing_snapshot_shows_a_fix_instead_of_crashing(tmp_path):
    os.environ["DASHBOARD_DATA"] = str(tmp_path / "nothing")
    try:
        at = AppTest.from_file(str(APP), default_timeout=120).run()
    finally:
        os.environ.pop("DASHBOARD_DATA", None)
    assert not at.exception
    assert "no results to show" in at.error[0].value
    assert "deploy.py run --sample" in at.code[0].value


def test_a_broken_table_is_contained_to_its_page(tmp_path):
    import shutil
    broken = tmp_path / "broken"
    shutil.copytree(data.PUBLISHED, broken)
    models = (broken / "models.csv").read_text(encoding="utf-8").replace("coef", "coefficient", 1)
    (broken / "models.csv").write_text(models, encoding="utf-8")
    at = page_test("answer_page", broken)
    assert "couldn't be drawn from the snapshot" in at.error[0].value  # the page says what went wrong
    other = page_test("actions_page", broken)
    assert not other.error and not other.exception                     # and the other pages still work


def test_empty_filters_explain_what_to_change():
    at = page_test("data_page")
    at.multiselect[0].set_value([]).run()
    assert any("No rows match" in i.value for i in at.info)
    at = page_test("actions_page")
    at.text_input[0].set_value("no such country").run()
    assert any("No countries match" in i.value for i in at.info)
    assert any("No forecast for a country matching" in i.value for i in at.info)
    at = page_test("wind_page")
    at.multiselect[0].set_value([]).run()
    assert any("No country-years match" in i.value for i in at.info)
    assert not at.exception


def test_wind_filters_refit_the_regressions_with_the_analysis_functions():
    at = page_test("wind_page")
    at.multiselect[1].set_value(["Large"]).run()  # the largest third of countries only
    assert not at.exception and not at.error
    assert any("refitted here on the filtered rows" in m.value for m in at.markdown)
    assert any("country-years" in json.loads(c.proto.spec)["title"].get("subtitle", "")
               for c in at.get("vega_lite_chart"))


def test_building_without_the_real_database_says_how_to_build_it(monkeypatch, tmp_path):
    import importlib

    from src.analysis import exploratory as ex
    sys.path.insert(0, str(data.ROOT / "scripts"))
    deploy = importlib.import_module("deploy")
    monkeypatch.setattr(ex, "REAL_DB", tmp_path / "rare_earth.db")
    with pytest.raises(SystemExit, match="real database isn't built.*run_pipeline.py"):
        deploy.main(["build"])


def test_presentation_path_rehearsal():
    """The path used in the final presentation (docs/deployment.md), step by step."""
    answer = page_test("answer_page")
    assert "Country size, not wind" in " ".join(m.value for m in answer.markdown)
    wind = page_test("wind_page")
    wind.toggle[0].set_value(True).run()                                 # remove country size
    assert any("r = 0.13" in c.value for c in wind.caption)
    assert list(wind.dataframe[0].value["result"]) == ["Supported", "Not supported", "Not supported",
                                                       "Not supported", "Supported"]
    actions = page_test("actions_page")
    table = actions.dataframe[0].value.set_index("country")["action"]
    assert table["India"] == "Grow" and table["Netherlands"] == "Verify"
    engine = page_test("engine_page")
    engine.select_slider[0].set_value(0.25).run()
    assert engine.slider[0].value == pytest.approx(0.8)
    limits = page_test("limits_page")
    assert not limits.exception and not limits.error


def test_threshold_explorer_follows_the_cost_ratio():
    at = page_test("engine_page")
    assert at.slider[0].value == pytest.approx(0.25)  # the engine's threshold at the 3:1 cost ratio
    at.select_slider[0].set_value(0.25).run()          # a false alarm now costs 4x a miss
    assert at.slider[0].value == pytest.approx(0.8)    # so the best threshold rises
    assert not at.exception
