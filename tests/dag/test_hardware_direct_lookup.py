"""Measured batch size must take precedence over the simulator's rounded key."""
from types import SimpleNamespace
import pandas as pd
from vidur.execution_time_predictor.sklearn_execution_time_predictor import SklearnExecutionTimePredictor


def test_real_decode_shape_precedes_rounded_profile():
    predictor = SimpleNamespace()
    predictor._compute_profile_has_context = True
    predictor._compute_profile_df = pd.DataFrame([
        {'phase_code': 1, 'input_tokens': 512, 'num_tokens': 1, 'time_stats.mlp_act.median': 0.1},
        {'phase_code': 1, 'input_tokens': 512, 'num_tokens': 8, 'time_stats.mlp_act.median': 0.8},
    ])
    batch = SimpleNamespace(num_prefill_tokens=0, size=1, total_num_tokens=1,
                            _total_num_tokens_rounded=8,
                            requests=[SimpleNamespace(num_processed_prefill_tokens=512)])
    assert SklearnExecutionTimePredictor._get_compute_prediction(predictor, 'mlp_act', batch) == 0.1
