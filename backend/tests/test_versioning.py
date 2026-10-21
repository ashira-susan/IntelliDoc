from datetime import datetime, timedelta

from app.algorithms.versioning import (
    date_proximity, family_score, filename_similarity,
    group_indices, normalize_filename,
)


def test_version_noise_removed():
    assert normalize_filename("ML_Assignment_Final_v2.pdf") == "ml assignment"
    assert normalize_filename("assignment_final2.docx") == "assignment"
    assert normalize_filename("CN Notes New.pdf") == "cn notes"


def test_non_version_numbers_kept():
    assert normalize_filename("assignment_1.pdf") != normalize_filename("assignment_2.pdf")


def test_version_names_are_similar_different_names_are_not():
    assert filename_similarity("report.pdf", "report_final.pdf") > 0.95
    assert filename_similarity("report.pdf", "music_history.pdf") < 0.5


def test_date_proximity_boundaries():
    t = datetime(2026, 10, 1)
    assert date_proximity(t, t) == 1.0
    assert date_proximity(t, t + timedelta(days=30)) == 0.0
    assert date_proximity(t, t + timedelta(days=90)) == 0.0
    assert date_proximity(t, None) is None


def test_missing_date_rescales_weights():
    assert abs(family_score(1.0, 1.0, None) - 1.0) < 1e-9
    assert abs(family_score(1.0, 1.0, 1.0) - 1.0) < 1e-9


def test_grouping_is_transitive():
    groups = group_indices(5, [(0, 1), (1, 2)])
    assert [sorted(g) for g in groups] == [[0, 1, 2]]