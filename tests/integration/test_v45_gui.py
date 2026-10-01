import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtWidgets import QApplication,QDialog
from PySide6.QtCore import QTimer
from pokerchip.ui.main_window import MainWindow
from pokerchip.core.config import create_project


def test_v45_fullscreen_restores_view_and_stale_frame_cannot_edit(tmp_path):
    app=QApplication.instance() or QApplication([])
    create_project(tmp_path)
    w=MainWindow(tmp_path);w.show();app.processEvents()
    w.tabs.setCurrentIndex(2);host=w.image_view.parentWidget();parent=host.parentWidget()
    QTimer.singleShot(30,lambda:w._full_dialog.accept())
    w.full_review();app.processEvents()
    assert host.parentWidget() is parent and w._full_dialog is None
    w.current_exp={'id':'a'};w.current_frame=7;w.displayed_frame=6
    with pytest.raises(ValueError,match='표시될 때'):w.require_editable_frame()
    w.displayed_frame=7;w.busy=True
    with pytest.raises(ValueError,match='계산 중'):w.require_editable_frame()
    w.busy=False;w.current_exp=None;w.close();app.processEvents()


def test_frame_shortcuts_do_not_steal_spinbox_editing(tmp_path):
    app=QApplication.instance() or QApplication([]);create_project(tmp_path)
    w=MainWindow(tmp_path);w.show();w.tabs.setCurrentIndex(2);app.processEvents()
    w.frame_spin.setFocus();app.processEvents()
    assert not w.review_shortcuts_allowed()
    w.image_view.setFocus();app.processEvents()
    w.tabs.setCurrentIndex(0);app.processEvents()
    assert not w.review_shortcuts_allowed()
    w.close();app.processEvents()
