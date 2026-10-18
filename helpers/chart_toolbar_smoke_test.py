"""Regression checks for Plotly toolbar behavior across AI Macro chart roles."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Test the shared chart wrapper without requiring a running Streamlit session.
streamlit_stub = types.ModuleType("streamlit")
streamlit_stub.plotly_chart = Mock(return_value={"selection": {"points": []}})
streamlit_stub.markdown = Mock()
with patch.dict(sys.modules, {"streamlit": streamlit_stub}):
    from rendering.visual_system import DEFAULT_PLOTLY_CONFIG, render_plotly_chart


class ChartToolbarSmokeTest(unittest.TestCase):
    def setUp(self):
        streamlit_stub.plotly_chart.reset_mock()
        streamlit_stub.markdown.reset_mock()
        self.figure = go.Figure(go.Scatter(x=[0, 1], y=[1, 2]))

    def render(self, *, key="toolbar-test", **kwargs):
        result = render_plotly_chart(self.figure, key=key, **kwargs)
        return result, streamlit_stub.plotly_chart.call_args.kwargs

    def test_toolbar_visible_when_legacy_chart_disables_it(self):
        _, kwargs = self.render(config={"displayModeBar": False, "responsive": False})
        self.assertIs(kwargs["config"]["displayModeBar"], True)
        self.assertIs(kwargs["config"]["responsive"], True)
        self.assertIs(kwargs["config"]["scrollZoom"], False)
        self.assertIs(kwargs["config"]["displaylogo"], False)

    def test_toolbar_visible_for_default_and_trend_chart(self):
        for role in (None, "trend", "pipeline"):
            with self.subTest(role=role):
                _, kwargs = self.render(role=role)
                self.assertIs(kwargs["config"]["displayModeBar"], True)

    def test_map_keeps_wheel_zoom_and_toolbar(self):
        _, kwargs = self.render(role="map", config={"displayModeBar": False})
        self.assertIs(kwargs["config"]["displayModeBar"], True)
        self.assertIs(kwargs["config"]["scrollZoom"], True)

    def test_chart_selection_and_unrelated_config_preserved(self):
        result, kwargs = self.render(
            on_select="rerun", selection_mode="points",
            config={"displayModeBar": False, "doubleClick": "reset", "scrollZoom": False},
        )
        self.assertEqual(result, {"selection": {"points": []}})
        self.assertEqual(kwargs["on_select"], "rerun")
        self.assertEqual(kwargs["selection_mode"], "points")
        self.assertEqual(kwargs["config"]["doubleClick"], "reset")
        self.assertIs(kwargs["config"]["displayModeBar"], True)
        self.assertNotIn("displayModeBar", DEFAULT_PLOTLY_CONFIG)


if __name__ == "__main__":
    unittest.main()
