"""Orchestrate data queries, chart generation, and Jinja2 template rendering."""

from __future__ import annotations

import logging
from pathlib import Path

import plotly.offline as plo

from savage_trade_evaluator.analysis import org_quality, sell_high
from savage_trade_evaluator.modeling import v3 as v3_module
from savage_trade_evaluator.reports import charts

logger = logging.getLogger(__name__)


def _fig_div(fig: object) -> str:
    """Render a Plotly Figure to an HTML div string."""
    return plo.plot(fig, output_type="div", include_plotlyjs=False)  # type: ignore[call-overload]


def build_findings_report(out_path: Path | None = None) -> Path:
    """Generate the main research findings HTML report.

    Runs: org_quality_map, sell_high decomposition, and renders template.
    Does NOT run the V3 backtest (slow — that's build_backtest_report).
    Returns the path to the written HTML file.
    """
    if out_path is None:
        out_path = Path("trade-eval-findings.html")

    logger.info("loading org quality map…")
    oq = org_quality.org_quality_map()

    logger.info("loading sell-high decomposition…")
    sell_summary = sell_high.all_regime_summary()

    logger.info("building charts…")
    org_chart = _fig_div(charts.org_quality_scatter(oq))
    sell_chart = _fig_div(charts.sell_high_bars(sell_summary))

    # Org quality top/bottom 5 for the prose table
    top5 = oq.nlargest(5, "total_dev_war")[
        ["franchise", "full_name", "total_dev_war", "trade_delta", "quadrant"]
    ]
    bot5 = oq.nsmallest(5, "total_dev_war")[
        ["franchise", "full_name", "total_dev_war", "trade_delta", "quadrant"]
    ]

    # Sell-high: TEX-Daniels row detail
    tex = sell_summary[sell_summary["regime"] == "TEX_Jon Daniels"]
    tex_row = tex.iloc[0].to_dict() if not tex.empty else {}

    from jinja2 import Environment, PackageLoader

    env = Environment(
        loader=PackageLoader("savage_trade_evaluator.reports", "templates"),
        autoescape=True,
    )
    tmpl = env.get_template("findings.html.jinja2")

    html = tmpl.render(
        org_chart=org_chart,
        sell_chart=sell_chart,
        top5=top5.to_dict(orient="records"),
        bot5=bot5.to_dict(orient="records"),
        tex_row=tex_row,
        sell_summary=sell_summary.to_dict(orient="records"),
        oq_median_dev=float(oq["total_dev_war"].median()),
        oq_median_trade=float(oq["trade_delta"].median()),
        n_regimes=len(sell_summary),
    )

    out_path.write_text(html, encoding="utf-8")
    logger.info("wrote %s (%d bytes)", out_path, len(html))
    return out_path


def build_backtest_report(
    outcomes: list[str] | None = None,
    out_path: Path | None = None,
    train_end: int = 2020,
    test_end: int = 2024,
) -> Path:
    """Generate the V3 backtest HTML report (runs MCMC — slow).

    Fits V3 for each outcome and renders calibration + coefficient charts.
    Returns the path to the written HTML file.
    """
    if out_path is None:
        out_path = Path("trade-eval-backtest.html")
    if outcomes is None:
        outcomes = ["xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus"]

    results: dict[str, v3_module.V3BacktestResult] = {}
    for outcome in outcomes:
        logger.info("fitting V3 for %s…", outcome)
        try:
            results[outcome] = v3_module.backtest_outcome_v3(
                outcome=outcome, train_end_season=train_end, test_end_season=test_end,
            )
        except ValueError as exc:
            logger.warning("skipped %s: %s", outcome, exc)

    if not results:
        msg = "No outcomes produced a valid backtest result"
        raise RuntimeError(msg)

    logger.info("building backtest charts…")
    summary_chart = _fig_div(charts.backtest_metrics_table(results))

    outcome_sections = []
    credible_dfs: dict[str, object] = {}
    for outcome, result in results.items():
        cal_chart = _fig_div(charts.calibration_scatter(result.test_predictions, outcome))
        coef_chart = _fig_div(charts.coefficient_forest(result.credible_features, outcome))
        credible_dfs[outcome] = result.credible_features
        outcome_sections.append({
            "outcome": outcome,
            "train_n": result.train_n,
            "test_n": result.test_n,
            "mae": result.test_mae,
            "crps": result.test_crps,
            "coverage_90": result.coverage_90,
            "n_credible": int(result.credible_features["credible"].sum()),
            "cal_chart": cal_chart,
            "coef_chart": coef_chart,
            "credible_rows": result.credible_features[result.credible_features["credible"]].to_dict(
                orient="records"
            ),
        })

    heatmap_chart = _fig_div(charts.feature_credibility_heatmap(credible_dfs))  # type: ignore[arg-type]

    from jinja2 import Environment, PackageLoader

    env = Environment(
        loader=PackageLoader("savage_trade_evaluator.reports", "templates"),
        autoescape=True,
    )
    tmpl = env.get_template("backtest.html.jinja2")
    html = tmpl.render(
        summary_chart=summary_chart,
        outcome_sections=outcome_sections,
        heatmap_chart=heatmap_chart,
        train_end=train_end,
        test_end=test_end,
    )

    out_path.write_text(html, encoding="utf-8")
    logger.info("wrote %s (%d bytes)", out_path, len(html))
    return out_path
