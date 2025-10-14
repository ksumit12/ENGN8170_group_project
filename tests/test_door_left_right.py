from app.direction_classifier import DirectionClassifier, LRParams


def test_classifier_constructs():
    params = LRParams(
        active_dbm=-70, energy_dbm=-65, delta_db=8, dwell_s=0.2,
        window_s=1.2, tau_min_s=0.12, cooldown_s=3.0,
        slope_min_db_per_s=10.0, min_peak_sep_s=0.12,
    )
    clf = DirectionClassifier(params, {"lag_positive": "LEAVE", "lag_negative": "ENTER"}, logger=None)
    assert clf is not None


