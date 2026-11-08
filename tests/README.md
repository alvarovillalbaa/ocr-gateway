# Focused native chart checks

`integration/test_native_ooxml_charts.py`: 27 authored Python cases against
the actual local ZIP/XML parser. `integration/native-ooxml-charts.test.mjs`:
18 Node cases through real local subprocesses, normalization/routing and an
authenticated loopback SDK/server. `helpers/ooxml_chart_fixtures.py` independently
encodes bounded synthetic OOXML; it never imports the product encoder.

The [approved packet](../docs/proposals/native-ooxml-chart-checks.md) runs these
45 cases against fresh installed npm/Python artifacts. Explicit package-root
overrides keep installed execution separate from source execution, and Python
asserts import locations. The existing ten React cases remain closed/separate.
Fixtures are authored data: no real uploads, provider calls, model, database,
browser or paid service. Native caches are not rendered-chart interpretation.

The [first invocation](../docs/results/2026/11-08/native-ooxml-charts-attempt-1.md)
stopped before all 45 cases at a build prerequisite; it supplies no functional
pass. The changed control installs one pinned build backend in an isolated
runner environment and executes the full new scope afresh.
