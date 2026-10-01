import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
import time
from PySide6.QtWidgets import QApplication,QPushButton,QFileDialog
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPoint
from pokerchip.gui_v2 import MainWindow
from pokerchip.storage import read_json


def wait(app,condition,timeout=40):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:
        app.processEvents();time.sleep(.02)
    assert condition()


def test_gui_real_widgets_workflow(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    folder=tmp_path/"GUI 한글 데모";folder.mkdir()
    monkeypatch.setattr(QFileDialog,"getExistingDirectory",lambda *a,**k:str(folder))
    w=MainWindow();errors=[];w.error=errors.append;w.show();app.processEvents()
    def click(text):
        button=next(b for b in w.findChildren(QPushButton) if b.text()==text)
        QTest.mouseClick(button,Qt.MouseButton.LeftButton);app.processEvents()
    click("합성 데모 만들기");wait(app,lambda:w.project is not None and not w.busy)
    assert w.queue_table.rowCount()==1
    click("모두 분석 / 재개");wait(app,lambda:w.batch is not None and w.batch.thread is not None and not w.batch.thread.is_alive(),80)
    app.processEvents();assert not errors
    assert w.project["experiments"][0]["status"]=="complete"
    w.queue_table.selectRow(0);click("선택 영상 검토");wait(app,lambda:w.original_image is not None)
    assert len(w.current_rows)==3
    w.slider.setValue(20);wait(app,lambda:w.current_frame==20 and w.frame_label.text().startswith("프레임 20"))
    monkeypatch.setattr(w,"reason",lambda:"synthetic visible edge correction")
    w.chip_choice.setCurrentText("chip_1");w.click_mode.setCurrentText("중심 보정 클릭")
    row=w.selected_row();x,y=row["raw_center_px"];rect=w.image_view.target
    point=QPoint(round(rect.x()+x*rect.width()/w.original_image.shape[1]),round(rect.y()+y*rect.height()/w.original_image.shape[0]))
    QTest.mouseClick(w.image_view,Qt.MouseButton.LeftButton,pos=point);app.processEvents()
    assert w.project["correction_cursor"]==1
    click("실행 취소");assert w.project["correction_cursor"]==0
    click("다시 실행");assert w.project["correction_cursor"]==1
    screenshot=os.environ.get("POKERCHIP_GUI_SCREENSHOT")
    if screenshot:
        w.log.setPlainText("자동 GUI 검사: 합성 생성 → 분석 → 프레임 이동 → 중심 수정 → undo/redo 완료.\n관측 검증 화면입니다. 실험 정확도 검증이 아닙니다.")
        app.processEvents();w.grab().save(screenshot)
    assert not errors
    w.close();app.processEvents()
