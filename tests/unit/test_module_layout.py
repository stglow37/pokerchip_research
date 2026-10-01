from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("legacy_name", "canonical_name"),
    [
        ("pokerchip.config", "pokerchip.core.config"),
        ("pokerchip.storage", "pokerchip.core.storage"),
        ("pokerchip.video", "pokerchip.measurement.video"),
        ("pokerchip.quality", "pokerchip.analysis.quality"),
        ("pokerchip.fitting", "pokerchip.models.fitting"),
        ("pokerchip.pipeline", "pokerchip.application.pipeline"),
        ("pokerchip.gui", "pokerchip.ui.main_window"),
        ("pokerchip.gui_v2", "pokerchip.ui.research_window"),
        ("pokerchip.legacy_gui", "pokerchip.ui.review_base"),
        ("pokerchip.physics.farkas", "pokerchip.models.physics.farkas"),
        ("pokerchip.physics.ifr", "pokerchip.models.physics.ifr"),
    ],
)
def test_legacy_module_is_canonical_module(legacy_name: str, canonical_name: str) -> None:
    assert importlib.import_module(legacy_name) is importlib.import_module(canonical_name)


def test_analysis_package_keeps_kinematics_api() -> None:
    legacy = importlib.import_module("pokerchip.analysis")
    canonical = importlib.import_module("pokerchip.analysis.kinematics")
    assert legacy.kinematic_at is canonical.kinematic_at
