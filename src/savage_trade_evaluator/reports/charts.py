"""Plotly chart factories for research findings reports.

Each function accepts pre-computed DataFrames and returns a Figure that can
be embedded in HTML via plotly.offline.plot(..., output_type="div").
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# Colour palette — consistent across all charts
_GREEN = "#2ecc71"
_YELLOW = "#f1c40f"
_GRAY = "#95a5a6"
_RED = "#e74c3c"
_BLUE = "#3498db"
_DARK = "#2c3e50"
_BG = "#0f1117"
_PANEL = "#1a1d27"
_TEXT = "#ecf0f1"

_BASE_LAYOUT = dict(
    paper_bgcolor=_BG,
    plot_bgcolor=_PANEL,
    font=dict(color=_TEXT, family="Inter, system-ui, sans-serif"),
    margin=dict(l=60, r=40, t=60, b=60),
    hoverlabel=dict(bgcolor=_DARK, font_size=13),
)


def org_quality_scatter(df: pd.DataFrame) -> go.Figure:
    """R-31: 2D scatter of franchise dev WAR vs mean trade Δ WAR.

    df must have columns: franchise, full_name, total_dev_war, trade_delta, quadrant.
    """
    median_dev = df["total_dev_war"].median()
    median_trade = df["trade_delta"].median()

    color_map = {
        "HIGH-DEV / POS-TRADE": _GREEN,
        "HIGH-DEV / NEG-TRADE": _YELLOW,
        "LOW-DEV / POS-TRADE": _BLUE,
        "LOW-DEV / NEG-TRADE": _RED,
    }

    fig = go.Figure()

    # Quadrant shading
    x_max = df["total_dev_war"].max() * 1.08
    x_min = df["total_dev_war"].min() * 0.92
    y_max = df["trade_delta"].max() + 0.15
    y_min = df["trade_delta"].min() - 0.15

    _quadrant_shading = [
        ((median_dev, x_max), (median_trade, y_max), "rgba(46,204,113,0.07)"),
        ((x_min, median_dev), (median_trade, y_max), "rgba(52,152,219,0.07)"),
        ((median_dev, x_max), (y_min, median_trade), "rgba(241,196,15,0.07)"),
        ((x_min, median_dev), (y_min, median_trade), "rgba(231,76,60,0.07)"),
    ]
    for (x0, x1), (y0, y1), color in _quadrant_shading:
        fig.add_shape(
            type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
            fillcolor=color, line_width=0, layer="below",
        )

    # Median lines
    fig.add_hline(y=median_trade, line_dash="dot", line_color="rgba(255,255,255,0.2)", line_width=1)
    fig.add_vline(x=median_dev, line_dash="dot", line_color="rgba(255,255,255,0.2)", line_width=1)

    # Data points
    for quadrant, group in df.groupby("quadrant"):
        fig.add_trace(go.Scatter(
            x=group["total_dev_war"],
            y=group["trade_delta"],
            mode="markers+text",
            name=quadrant,
            text=group["franchise"],
            textposition="top center",
            textfont=dict(size=10, color=color_map.get(str(quadrant), _GRAY)),
            marker=dict(
                size=11,
                color=color_map.get(str(quadrant), _GRAY),
                line=dict(width=1, color="rgba(255,255,255,0.3)"),
            ),
            customdata=group[["full_name", "n_trades", "n_mlb_debutees"]].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Dev WAR: %{x:.0f}<br>"
                "Trade Δ: %{y:+.3f} WAR/trade<br>"
                "Trades analyzed: %{customdata[1]}<br>"
                "MLB debutees: %{customdata[2]}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="Franchise Org Quality Map — Dev Credit vs Trade Outcome (R-31)",
            font=dict(size=15),
        ),
        xaxis=dict(
            title="Total Dev WAR (career WAR of players who debuted for this franchise, 1990+)",
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.15)",
        ),
        yaxis=dict(
            title="Mean Trade Delta WAR (T+1 minus T-1, departed players, 1990+)",
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.25)",
            tickformat="+.3f",
        ),
        legend=dict(
            title="Quadrant",
            bgcolor="rgba(0,0,0,0.4)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
        ),
        height=560,
    )

    # Annotate noteworthy teams
    for team, note in [
        ("HOU", "Only HIGH-DEV / POS-TRADE"),
        ("STL", "Best trade Δ"),
        ("CLE", "Best dev pipeline"),
        ("SFG", "Last on both axes"),
    ]:
        row = df[df["franchise"] == team]
        if row.empty:
            continue
        fig.add_annotation(
            x=float(row["total_dev_war"].iloc[0]),
            y=float(row["trade_delta"].iloc[0]),
            text=note,
            showarrow=True,
            arrowhead=2,
            arrowsize=0.8,
            arrowcolor="rgba(255,255,255,0.4)",
            ax=40, ay=-30,
            font=dict(size=10, color=_TEXT),
            bgcolor="rgba(0,0,0,0.5)",
            bordercolor="rgba(255,255,255,0.2)",
        )

    return fig


def coefficient_forest(credible_features: pd.DataFrame, outcome: str = "") -> go.Figure:
    """Horizontal forest plot of posterior beta estimates with 90% CI.

    credible_features must have columns: feature, mean_beta, p05, p95,
    directional_mass, credible (bool).
    """
    df = credible_features.copy()
    df = df.sort_values("mean_beta")

    colors = df["credible"].map({True: _GREEN, False: _YELLOW}).tolist()
    # Null features (mass < 85%) get gray
    null_mask = df["directional_mass"] < 0.85
    for i, is_null in enumerate(null_mask):
        if is_null:
            colors[i] = _GRAY

    fig = go.Figure()

    # Zero reference
    fig.add_vline(x=0, line_color="rgba(255,255,255,0.3)", line_width=1)

    fig.add_trace(go.Scatter(
        x=df["mean_beta"],
        y=df["feature"],
        mode="markers",
        marker=dict(
            color=colors,
            size=10,
            symbol="circle",
            line=dict(width=1, color="rgba(255,255,255,0.2)"),
        ),
        error_x=dict(
            type="data",
            symmetric=False,
            array=(df["p95"] - df["mean_beta"]).tolist(),
            arrayminus=(df["mean_beta"] - df["p05"]).tolist(),
            color="rgba(255,255,255,0.35)",
            thickness=1.5,
            width=4,
        ),
        customdata=df[["directional_mass", "p05", "p95", "credible"]].values,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "β = %{x:.3f}<br>"
            "90% CI: [%{customdata[1]:.3f}, %{customdata[2]:.3f}]<br>"
            "Directional mass: %{customdata[0]:.0%}<br>"
            "Credible: %{customdata[3]}<extra></extra>"
        ),
        showlegend=False,
    ))

    # Legend annotation
    for color, label in [(_GREEN, "Credible (CI ∉ 0, mass ≥ 95%)"),
                          (_YELLOW, "Directional (mass ≥ 85%)"),
                          (_GRAY, "Null")]:
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers",
            marker=dict(color=color, size=10),
            name=label,
        ))

    title = f"Posterior β Estimates — {outcome}" if outcome else "Posterior β Estimates"
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=title, font=dict(size=15)),
        xaxis=dict(
            title="Standardized β (posterior mean, 90% credible interval)",
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.2)",
        ),
        yaxis=dict(
            title="",
            automargin=True,
            tickfont=dict(size=11),
            gridcolor="rgba(255,255,255,0.04)",
        ),
        legend=dict(bgcolor="rgba(0,0,0,0.4)", borderwidth=1, bordercolor="rgba(255,255,255,0.1)"),
        height=max(320, 28 * len(df) + 100),
        margin=dict(l=280, r=40, t=60, b=60),
    )
    return fig


def calibration_scatter(test_predictions: pd.DataFrame, outcome: str = "") -> go.Figure:
    """Predicted vs actual scatter with 90% PI bands."""
    df = test_predictions.dropna(subset=["y_true", "y_pred_mean"]).copy()

    in_band = ((df["y_true"] >= df["y_pred_p05"]) & (df["y_true"] <= df["y_pred_p95"]))
    coverage = float(in_band.mean())

    ref_min = min(float(df["y_true"].min()), float(df["y_pred_mean"].min()))
    ref_max = max(float(df["y_true"].max()), float(df["y_pred_mean"].max()))
    pad = (ref_max - ref_min) * 0.05

    fig = go.Figure()

    # 90% PI as error bars
    fig.add_trace(go.Scatter(
        x=df["y_pred_mean"],
        y=df["y_true"],
        mode="markers",
        marker=dict(
            color=df["y_true"].apply(lambda v: _GREEN if v >= 0 else _RED),
            size=6,
            opacity=0.6,
            line=dict(width=0),
        ),
        error_x=dict(
            type="data",
            symmetric=False,
            array=(df["y_pred_p95"] - df["y_pred_mean"]).tolist(),
            arrayminus=(df["y_pred_mean"] - df["y_pred_p05"]).tolist(),
            color="rgba(255,255,255,0.15)",
            thickness=1,
            width=0,
        ),
        customdata=df[["trade_season", "receiver_bref"]].values,
        hovertemplate=(
            "Season: %{customdata[0]}<br>"
            "Team: %{customdata[1]}<br>"
            "Predicted: %{x:.3f}<br>"
            "Actual: %{y:.3f}<extra></extra>"
        ),
        name="Trade outcome",
    ))

    # Perfect-calibration line
    fig.add_trace(go.Scatter(
        x=[ref_min - pad, ref_max + pad],
        y=[ref_min - pad, ref_max + pad],
        mode="lines",
        line=dict(color="rgba(255,255,255,0.35)", dash="dot", width=1.5),
        name="Perfect calibration",
        hoverinfo="skip",
    ))

    title = f"Calibration — {outcome}" if outcome else "Calibration"
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text=f"{title}  |  90% PI coverage: {coverage:.1%}",
            font=dict(size=15),
        ),
        xaxis=dict(
            title="Predicted (posterior mean)",
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.15)",
            range=[ref_min - pad, ref_max + pad],
        ),
        yaxis=dict(
            title="Actual",
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.15)",
            range=[ref_min - pad, ref_max + pad],
        ),
        height=440,
    )
    return fig


def sell_high_bars(summary: pd.DataFrame) -> go.Figure:
    """R-29/R-30: mean Δ WAR by player bucket across selected regimes.

    summary must have columns: regime, vet_mean, young_mean, middle_mean, mean_delta_all.
    Show top-N most-negative overall regimes for clarity.
    """
    df = summary.sort_values("mean_delta_all").head(12).copy()
    short_regime = df["regime"].str.split("_").str[1:].str.join(" ")

    fig = go.Figure()
    for col, color, label in [
        ("vet_mean", _RED, "Veteran-at-peak (pre ≥2 WAR, ≥6 yr exp)"),
        ("young_mean", _GREEN, "Young prospect (pre ≤1 WAR, ≤4 yr exp)"),
        ("middle_mean", _GRAY, "Middle (everything else)"),
    ]:
        fig.add_trace(go.Bar(
            name=label,
            x=short_regime.tolist(),
            y=df[col].tolist(),
            marker_color=color,
            opacity=0.85,
            customdata=df[["regime", col]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>Mean Δ WAR: %{y:+.3f}<extra></extra>",
        ))

    # Overall line
    fig.add_trace(go.Scatter(
        x=short_regime.tolist(),
        y=df["mean_delta_all"].tolist(),
        mode="markers",
        marker=dict(symbol="line-ew", size=14, color="white", line=dict(width=2, color="white")),
        name="Overall mean Δ",
        hovertemplate="Overall: %{y:+.3f}<extra></extra>",
    ))

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_width=1)

    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="Sell-High vs System-Tax: Δ WAR by Player Maturity Bucket (R-29/R-30)",
            font=dict(size=15),
        ),
        xaxis=dict(title="GM Regime (most negative overall → right)", tickangle=-30),
        yaxis=dict(
            title="Mean Delta WAR (T+1 - T-1)",
            gridcolor="rgba(255,255,255,0.06)",
            zerolinecolor="rgba(255,255,255,0.25)",
            tickformat="+.2f",
        ),
        barmode="group",
        legend=dict(bgcolor="rgba(0,0,0,0.4)", borderwidth=1, bordercolor="rgba(255,255,255,0.1)"),
        height=480,
    )
    return fig


def feature_credibility_heatmap(results_by_outcome: dict[str, pd.DataFrame]) -> go.Figure:
    """R-19/D-26: feature-by-outcome heatmap of directional_mass.

    results_by_outcome: {outcome_name: credible_features DataFrame}
    Each DataFrame must have columns: feature, directional_mass, credible.
    """
    outcomes = list(results_by_outcome.keys())
    all_features: list[str] = []
    for df in results_by_outcome.values():
        for f in df["feature"].tolist():
            if f not in all_features:
                all_features.append(f)

    z: list[list[float]] = []
    annotations: list[dict] = []
    for feat in all_features:
        row: list[float] = []
        for oi, outcome in enumerate(outcomes):
            df = results_by_outcome[outcome]
            match = df[df["feature"] == feat]
            if match.empty:
                row.append(float("nan"))
            else:
                col = "mass_signed" if "mass_signed" in match.columns else "directional_mass"
                mass = float(match[col].iloc[0])
                row.append(mass)
                # Annotate credible cells
                if bool(match["credible"].iloc[0]):
                    annotations.append(dict(
                        x=oi, y=all_features.index(feat),
                        text="★", showarrow=False,
                        font=dict(size=11, color="white"),
                    ))
        z.append(row)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=outcomes,
        y=all_features,
        colorscale=[
            [0.0, "rgba(231,76,60,0.8)"],
            [0.5, "rgba(44,62,80,0.6)"],
            [1.0, "rgba(46,204,113,0.9)"],
        ],
        zmid=0.85,
        zmin=0.5,
        zmax=1.0,
        colorbar=dict(
            title="Directional mass",
            tickformat=".0%",
            bgcolor="rgba(0,0,0,0)",
            bordercolor="rgba(255,255,255,0.2)",
            tickfont=dict(color=_TEXT),
        ),
        hovertemplate="Feature: %{y}<br>Outcome: %{x}<br>Mass: %{z:.0%}<extra></extra>",
    ))

    for ann in annotations:
        fig.add_annotation(**ann)

    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text="Feature Credibility by Outcome (★ = credible, D-26 threshold) — R-19/R-22/R-35",
            font=dict(size=15),
        ),
        xaxis=dict(title="Outcome", side="top", tickangle=-20),
        yaxis=dict(title="", automargin=True, tickfont=dict(size=10)),
        height=max(400, 22 * len(all_features) + 120),
        margin=dict(l=300, r=80, t=100, b=40),
    )
    return fig


def backtest_metrics_table(results: dict[str, object]) -> go.Figure:
    """Simple table of MAE, CRPS, 90% coverage across all outcomes."""
    rows = []
    for outcome, r in results.items():
        ncred = int(r.credible_features["credible"].sum())  # type: ignore[union-attr]
        rows.append({
            "Outcome": outcome,
            "Train n": r.train_n,  # type: ignore[union-attr]
            "Test n": r.test_n,  # type: ignore[union-attr]
            "MAE": f"{r.test_mae:.4f}",  # type: ignore[union-attr]
            "CRPS": f"{r.test_crps:.4f}",  # type: ignore[union-attr]
            "90% Coverage": f"{r.coverage_90:.1%}",  # type: ignore[union-attr]
            "Credible Features": ncred,
        })
    df = pd.DataFrame(rows)

    fig = go.Figure(go.Table(
        header=dict(
            values=list(df.columns),
            fill_color=_DARK,
            font=dict(color=_TEXT, size=12, family="Inter, monospace"),
            align="left",
            line_color="rgba(255,255,255,0.1)",
        ),
        cells=dict(
            values=[df[c].tolist() for c in df.columns],
            fill_color=[[_PANEL if i % 2 == 0 else "rgba(30,35,50,1)" for i in range(len(df))]
                        for _ in df.columns],
            font=dict(color=_TEXT, size=11, family="Inter, monospace"),
            align="left",
            line_color="rgba(255,255,255,0.05)",
        ),
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text="V3 Backtest Summary — All Outcomes", font=dict(size=15)),
        height=max(200, 40 * len(df) + 80),
        margin=dict(l=20, r=20, t=60, b=20),
    )
    return fig
