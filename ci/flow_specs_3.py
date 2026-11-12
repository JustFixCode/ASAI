"""Subset of the reviewed ASAI flow specifications."""
from __future__ import annotations

FLOW_SPECS_PART_3: dict[str, tuple[str, tuple[str, ...]]] = {
    'interfaces-market-data/app-no-submission': ('interfaces-market-data', ('test_app.AppTests.test_no_network_or_broker_submission',)),
    'interfaces-market-data/pipeline-regressions': ('interfaces-market-data', ('test_pipeline_regressions.PipelineRegressionTests.test_offline_integrated_app_never_submits_to_broker_or_network', 'test_pipeline_regressions.PipelineRegressionTests.test_quote_freshness_and_provenance_remain_untrusted_offline_diagnostics')),
}
