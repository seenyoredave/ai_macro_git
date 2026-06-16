### visualization utilities used throughout the AI Macro Dashboard.


#import streamlit as st 
import pandas as pd
import numpy as np 
import plotly.graph_objects as go

from helpers.labels import sector_display_name
from config.metric_definitions import METRIC_DEFINITIONS 


################################
# NaN SAFE GAUGE HELPER 
################################

def safe_gauge_value(value, default=0):
    return default if pd.isna(value) else value

###############################
# GAUGE GRADIENT
###############################

def gauge_gradient_steps(start, end, colors, repeats=1):

    expanded = []

    for color in colors:
        expanded.extend([color] * repeats)

    step_size = (end - start) / len(expanded)

    steps = []

    for i, color in enumerate(expanded):

        steps.append({
            "range": [
                start + i * step_size,
                start + (i + 1) * step_size
            ],
            "color": color
        })

    return steps

GAUGE_COLORS = [
    "#111827",
    "#172554",
    "#1e3a8a",
    "#1d4ed8",
    "#2563eb",
    "#4f46e5",
    "#6d28d9",
    "#7c3aed",
    "#a78bfa",
    "#ddd6fe",
]

###############################
# MACRO DASHBOARD GAUGES
###############################
 
def build_maturity_gauge(value):

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=safe_gauge_value(value),      
        title={"text": "Maturation Cycle"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {
                "color": "#a78bfa"
            },
            "steps": gauge_gradient_steps(
                0,
                100,
                GAUGE_COLORS,
                repeats=5
            )
        }
    ))

    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=60, b=20),
        autosize=True
    )

    return fig

def build_divergence_gauge(value):

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=safe_gauge_value(value, default=0),     
        title={"text": "Divergence Estimate"},
        gauge={
            "axis": {"range": [-100, 100]},
            "bar": {
                "color": "#a78bfa"
            },
            "steps": gauge_gradient_steps(
                -100,
                100,
                GAUGE_COLORS,
                repeats=5
            )
        }
    ))

    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=60, b=20),
        autosize=True
    )

    return fig

def build_power_stress_gauge(value):

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=safe_gauge_value(value),
        title={"text": "Power Stress Index"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#a78bfa"},
            "steps": gauge_gradient_steps(
                0,
                100,
                GAUGE_COLORS,
                repeats=5
            )
        }
    ))

    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=60, b=20),
        autosize=True
    )

    return fig

def build_concentration_gauge(value):

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=safe_gauge_value(value),
        title={"text": "Concentration HHI"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": "#a78bfa"},
            "steps": gauge_gradient_steps(
                0,
                100,
                GAUGE_COLORS,
                repeats=5
            )
        }
    ))

    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=60, b=20),
        autosize=True
    )

    return fig

###############################
# MACRO DASHBOARD GRAPHS
###############################

def build_positioning_map(macro_df):
    fig_mv = go.Figure()

    fig_mv.add_trace(

        go.Scatter(

            x=macro_df["Forward P/E"],

            y=macro_df["Avg Return"] * 100,

            mode="markers",
            
            hovertemplate=
            "<b>%{text}</b><br>" +
            "Forward P/E: %{x:.1f}<br>" +
            "1Y Return: %{y:.1f}%",

            text=macro_df["Sector"].apply(sector_display_name),

            textposition="top center",

            marker=dict(

                size=np.clip(
                    macro_df["Heat"]/4,
                    8,
                    22
                ),

                color=macro_df["Cycle Score"],

                colorscale="Viridis",

                opacity=0.75,
                
                showscale=True,

                colorbar=dict(
                    title="Maturity"
                )
            )
        )
    )

    fig_mv.update_layout(

        xaxis_title="Forward P/E",

        yaxis_title="1Y Return (%)",

    template="plotly_white",

    height=500
    )

    x_series = pd.to_numeric(macro_df["Forward P/E"], errors="coerce")
    y_series = pd.to_numeric(macro_df["Avg Return"], errors="coerce") * 100

    x_min = x_series.min()
    x_max = x_series.max()

    y_min = y_series.min()
    y_max = y_series.max()

    if pd.isna(x_min) or pd.isna(x_max) or pd.isna(y_min) or pd.isna(y_max):
        return fig_mv

    pe_mid = (x_min + x_max) / 2
    ret_mid = (y_min + y_max) / 2
    
    fig_mv.add_vline(x=pe_mid,line_dash="dot")
    fig_mv.add_hline(y=ret_mid,line_dash="dot")

    fig_mv.add_annotation(
    x=pe_mid * 0.5,
    y=ret_mid * 2.3,
    text="Momentum",
    showarrow=False
    )

    fig_mv.add_annotation(
        x=pe_mid * 1.6,
        y=ret_mid * 2.3,
        text="Leaders",
        showarrow=False
    )

    fig_mv.add_annotation(
        x=pe_mid * 0.5,
        y=ret_mid * -0.2,
        text="Value",
        showarrow=False
    )

    fig_mv.add_annotation(
        x=pe_mid * 1.6,
        y=ret_mid * -0.2,
        text="Lagging",
        showarrow=False
    )

    return fig_mv
    
def build_rotation_matrix(macro_df):
    fig_rotation = go.Figure()

    fig_rotation.add_trace(

        go.Scatter(

            x=macro_df["Cycle Score"],

            y=macro_df["Heat"],

            mode="markers",

            text=macro_df["Sector"].apply(sector_display_name),

            textposition="top center",

            hovertemplate=
            "<b>%{text}</b><br>" +
            "Cycle Maturity: %{x:.0f}<br>" +
            "Heat: %{y:.0f}<extra></extra>",

            marker=dict(

                size=np.clip(
                    abs(macro_df["Avg Return"] * 100) / 2,
                    10,
                    30
                ),

                color=macro_df["Forward P/E"],

                colorscale="Viridis",
                
                opacity=0.75,

                showscale=True,

                colorbar=dict(
                    title="F P/E"
                )
            )
        )
    )

    fig_rotation.update_layout(

        xaxis_title="Cycle Maturity",

        yaxis_title="Pressure",

        template="plotly_white",

        height=500
    )
    
    temp_mid = pd.to_numeric(macro_df["Cycle Score"], errors="coerce").median()
    heat_mid = pd.to_numeric(macro_df["Heat"], errors="coerce").median()

    if pd.isna(temp_mid) or pd.isna(heat_mid):
        return fig_rotation

    fig_rotation.add_vline(
        x=temp_mid,
        line_dash="dot"
    )

    fig_rotation.add_hline(
        y=heat_mid,
        line_dash="dot"
    )

    fig_rotation.add_annotation(
        x=temp_mid * 0.5,
        y=heat_mid * 2.3,
        text="Opportunity",
        showarrow=False
    )

    fig_rotation.add_annotation(
        x=temp_mid * 1.6,
        y=heat_mid * 2.3,
        text="Crowded",
        showarrow=False
    )

    fig_rotation.add_annotation(
        x=temp_mid * 0.5,
        y=heat_mid * -0.2,
        text="Dead Money",
        showarrow=False
    )

    fig_rotation.add_annotation(
        x=temp_mid * 1.6,
        y=heat_mid * -0.2,
        text="Narrative Risk",
        showarrow=False
    )

    return fig_rotation

def factor_color(score):

    if pd.isna(score):
        return "#374151"

    if score < 25:
        return "#2563eb"

    elif score < 50:
        return "#60a5fa"

    elif score < 75:
        return "#bfdbfe"

    return "#ffffff"
   
   