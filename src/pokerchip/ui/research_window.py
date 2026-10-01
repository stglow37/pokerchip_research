"""Guided v2 desktop shell sharing the tested CLI engine and v1 review commands."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QListWidget,QTableWidget,QTableWidgetItem,QPlainTextEdit,QComboBox,QSpinBox,QGroupBox,
    QDialog,QFormLayout,QLineEdit,QFileDialog,QHeaderView,QCheckBox,QInputDialog,QSplitter,QMessageBox)
from .review_base import MainWindow as ReviewWindow
from .forms import SetupPanel,dialog,buttons,number
from ..core.config import register,save_project,COLORS
from ..core.storage import Records,read_json,atomic_json
from ..analysis.quality import project_status

STYLE="""
QMainWindow, QDialog {background:#f4f7fb; color:#182a3a;}
QWidget {font-family:'Malgun Gothic';font-size:10pt;}
QLabel {color:#20364a;}
QLabel#title {font-size:22pt;font-weight:700;color:#153f53;}
QLabel#subtitle {font-size:11pt;color:#546a7d;padding:4px 0;}
QPushButton {background:white;border:1px solid #cdd9e3;border-radius:6px;padding:8px 12px;color:#19394c;}
QPushButton:hover {background:#e8f1f7;border-color:#517c91;}
QPushButton:disabled {color:#9baab5;background:#f0f2f5;}
QPushButton#primary {background:#17667a;color:white;border:none;font-weight:600;}
QPushButton#primary:hover {background:#125466;}
QListWidget {background:#142f40;color:#d8e5ed;border:none;border-radius:8px;padding:10px;}
QListWidget::item {padding:15px 10px;border-radius:6px;}
QListWidget::item:selected {background:#28647a;color:white;font-weight:600;}
QGroupBox {background:white;border:1px solid #dce5ec;border-radius:8px;margin-top:14px;padding:14px;}
QGroupBox::title {subcontrol-origin:margin;left:12px;color:#2c566c;font-weight:600;}
QTableWidget {background:white;alternate-background-color:#f3f7fa;gridline-color:#e1e8ef;border:1px solid #d7e1e9;selection-background-color:#d5eaf3;selection-color:#152d40;}
QHeaderView::section {background:#e9f0f5;color:#315064;border:0;border-bottom:1px solid #d1dfe8;padding:8px;}
QLineEdit,QPlainTextEdit,QSpinBox,QDoubleSpinBox,QComboBox {background:white;color:#182f42;border:1px solid #ccd9e3;border-radius:4px;padding:6px;}
QTabWidget::pane {border:0;}
QTabBar::tab {padding:10px 16px;color:#3a566a;background:#e9eff4;}
QTabBar::tab:selected {background:white;color:#17667a;}
QStatusBar {background:#e6eef4;color:#385367;}
"""


def label(text,object_name=None):
    w=QLabel(text);w.setWordWrap(True)
    if object_name:w.setObjectName(object_name)
    return w


def table(headers):
    w=QTableWidget(0,len(headers));w.setHorizontalHeaderLabels(headers);w.setAlternatingRowColors(True)
    w.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    w.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    w.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    w.horizontalHeader().setStretchLastSection(True)
    return w


class MainWindow(ReviewWindow):
    def __init__(self,folder=None):
        super().__init__(None)
        self.setWindowTitle("PokerChip Research v2 · 실험 영상 분석")
        self.resize(1480,960);self.setMinimumSize(1080,720);self.setStyleSheet(STYLE)
        self.tabs.tabBar().hide()
        layout=self.centralWidget().layout();layout.removeWidget(self.tabs)
        self.nav=QListWidget();self.nav.setFixedWidth(195)
        self.pages=[5,1,0,2,3,4]
        self.nav.addItems(["연구 대시보드","1  촬영·보정 설정","2  영상 분석","3  관측·충돌 검토","4  피팅·검증","5  결과 내보내기"])
        body=QHBoxLayout();body.addWidget(self.nav);body.addWidget(self.tabs,1);layout.insertLayout(1,body,1)
        self.build_home()
        self.nav.currentRowChanged.connect(lambda row:self.tabs.setCurrentIndex(self.pages[row]) if row>=0 else None)
        self.tabs.currentChanged.connect(self.sync_nav)
        self.nav.setCurrentRow(0)
        self.log.setVisible(False);self.log.setMaximumBlockCount(2000)
        menu=self.menuBar().addMenu("도움말 / 진단")
        action=menu.addAction("작업 로그 표시");action.setCheckable(True);action.toggled.connect(self.log.setVisible)
        menu.addAction("사용 설명서",self.open_manual)
        menu.addAction("대시보드 새로고침",self.refresh_home)
        self.review_keys=[]
        for key,cb in [("Right",lambda:self.slider.setValue(self.slider.value()+1)),("Left",lambda:self.slider.setValue(self.slider.value()-1)),
                       ("Ctrl+Z",lambda:self.guarded(lambda:self.history(-1))),("Ctrl+Y",lambda:self.guarded(lambda:self.history(1))),
                       ("N",lambda:self.guarded(lambda:self.jump_issue(1))),("P",lambda:self.guarded(lambda:self.jump_issue(-1)))]:
            sc=QShortcut(QKeySequence(key),self);sc.activated.connect(lambda cb=cb:cb() if self.review_shortcuts_allowed() else None)
            # Disable, rather than swallow, shortcuts while text/spin controls own focus.
            self.review_keys.append(sc)
        QApplication.instance().focusChanged.connect(self.refresh_review_shortcuts)
        self.tabs.currentChanged.connect(self.refresh_review_shortcuts)
        self.refresh_home()
        if folder:self.load(folder)

    def review_shortcuts_allowed(self):
        from PySide6.QtWidgets import QAbstractSpinBox,QTextEdit
        return self.tabs.currentIndex()==2 and not isinstance(QApplication.focusWidget(),(QLineEdit,QAbstractSpinBox,QPlainTextEdit,QTextEdit))

    def refresh_review_shortcuts(self,*args):
        for shortcut in self.review_keys:shortcut.setEnabled(self.review_shortcuts_allowed())

    def sync_nav(self,index):
        if hasattr(self,"nav") and index in self.pages:
            self.nav.blockSignals(True);self.nav.setCurrentRow(self.pages.index(index));self.nav.blockSignals(False)

    def guarded(self,callback):
        try:return callback()
        except Exception as exc:
            # A form validation error must not clear the separate worker busy flag.
            message=f"{type(exc).__name__}: {exc}"
            if hasattr(self,"log"):self.log.appendPlainText(message)
            QMessageBox.warning(self,"작업 확인",message)

    def build_home(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"대시보드")
        v.addWidget(label("실험이 어디까지 검증되었나요?","title"))
        v.addWidget(label("분석 완료 · 측정 품질 · 물리모델 검증을 각각 확인합니다.","subtitle"))
        row=QHBoxLayout();v.addLayout(row);self.cards=[]
        for title in ("등록 영상","분석 완료","검토 프레임","정확도 검증"):
            box=QGroupBox(title);b=QVBoxLayout(box);value=label("—");value.setStyleSheet("font-size:20pt;font-weight:700;padding:14px;");b.addWidget(value);row.addWidget(box);self.cards.append(value)
        self.readiness=table(["준비 항목","상태","의미 / 다음 행동"]);self.readiness.setMaximumHeight(200);v.addWidget(self.readiness)
        self.readiness.cellDoubleClicked.connect(lambda r,c:self.tabs.setCurrentIndex(1))
        self.next_text=label("");self.next_text.setStyleSheet("background:#e1f0f3;padding:16px;border-radius:8px;font-size:11pt;");v.addWidget(self.next_text)
        self.home_table=table(["영상","작업 상태","관측 비율","검토 필요","충돌 승인/후보","정답 중심 RMSE"]);v.addWidget(self.home_table,1)
        self.home_table.cellDoubleClicked.connect(lambda r,c:self.guarded(lambda:self.select_experiment(r)))
        v.addWidget(label("관측 비율은 전체 관측 기회 중 검출된 행의 비율입니다. 독립 정답과 비교하기 전에는 '정확도'가 아닙니다."))
        bar=QHBoxLayout();v.addLayout(bar)
        self.button(bar,"촬영·보정 설정으로",lambda:self.tabs.setCurrentIndex(1))
        self.button(bar,"영상 등록·분석으로",lambda:self.tabs.setCurrentIndex(0)).setObjectName("primary")

    def refresh_home(self):
        if not hasattr(self,"cards"):return
        status=project_status(self.project,self.folder);exps=status["experiments"]
        self.cards[0].setText(str(len(exps)));self.cards[1].setText(str(sum(e["status"]=="complete" for e in exps)))
        self.cards[2].setText(str(sum(e["quality"].get("review_frame_count",0) for e in exps)))
        validated=0
        self.readiness.setRowCount(len(status["checks"]))
        for i,check in enumerate(status["checks"]):
            for j,k in enumerate(("label","state","detail")):self.readiness.setItem(i,j,QTableWidgetItem(check[k]))
        self.next_text.setText(status["next"])
        self.home_table.setRowCount(len(exps))
        for i,e in enumerate(exps):
            q=e["quality"];accuracy="미검증"
            exp=self.project["experiments"][i]
            if exp.get("last_run"):
                p=self.folder/exp["last_run"]/"export/label_validation.json"
                if p.exists():
                    result=read_json(p);r=result.get("center_rmse_px")
                    if r is not None:accuracy=f"{r:.3f} px / {result['complete_frames']} 라벨 프레임";validated+=1
            values=[e["name"],"이전 설정 · 재분석 필요" if e.get("stale") else self.status_text(e["status"]),f"{(q.get('observed_fraction_selected_intervals',q['observed_fraction_all_target_frames']) or 0):.1%}" if q else "—",
                    str(q.get("review_frame_count","—")),f"{q.get('fit_eligible_events',0)} / {q.get('event_candidates',0)}",accuracy]
            for j,value in enumerate(values):self.home_table.setItem(i,j,QTableWidgetItem(value))
        self.cards[3].setText(f"{validated}개 라벨 평가" if validated else "미측정")

    @staticmethod
    def status_text(s):
        return {"pending":"대기","complete":"처리 완료","failed":"실패","cancelled":"중단","detect":"원·표식 계측 중","kinematics":"속도·회전 계산 중","analysis":"사건 분석 중","running":"진행 중"}.get(s,str(s))

    def build_queue(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"분석")
        v.addWidget(label("영상을 넣고 관측을 시작하세요","title"));v.addWidget(label("원본은 변경하지 않습니다. 두 번 클릭하면 영상과 분석 결과를 검토합니다.","subtitle"))
        bar=QHBoxLayout();v.addLayout(bar)
        self.button(bar,"영상 여러 개 등록",self.add_videos)
        self.button(bar,"선택 조건 수정",self.edit_experiments)
        self.button(bar,"모두 분석 / 재개",self.start_batch).setObjectName("primary")
        self.button(bar,"선택 분석 / 재시도",lambda:self.start_batch(True))
        self.queue_table=table(["이름","세션","참여 칩","분석 구간","상태","experiment ID"])
        self.queue_table.setColumnHidden(5,True);v.addWidget(self.queue_table,1)
        self.queue_table.cellDoubleClicked.connect(lambda r,c:self.guarded(lambda:self.select_experiment(r)))
        bar=QHBoxLayout();v.addLayout(bar)
        for text,cb in [("선택 영상 검토",lambda:self.select_experiment(self.queue_table.currentRow())),("일시정지",lambda:self.batch.pause() if self.batch else None),
                        ("계속",lambda:self.batch.resume() if self.batch else None),("취소",lambda:self.batch.cancel() if self.batch else None),("원본 재연결",self.reconnect)]:self.button(bar,text,cb)
        self.queue_progress=label("준비 · 원 검출은 보정 전에도 가능합니다. 물리량 계산 상태는 대시보드에서 확인하세요.");v.addWidget(self.queue_progress)
        self.drop_kind=QComboBox();self.drop_kind.addItems(["끌어놓기: 실험 영상","끌어놓기: ChArUco 보정 영상"]);v.addWidget(self.drop_kind)

    def add_paths(self,paths):
        self.require()
        count,ok=QInputDialog.getInt(self,"영상 참여 칩 수","등록하는 영상의 칩 수 (다르면 나중에 개별 수정)",2,1,3)
        if not ok:return
        register(self.folder,self.project,paths,list(COLORS)[:count]);self.refresh_queue();self.refresh_home()

    def edit_experiments(self):
        selected=self.selected_experiments();first=selected[0];d,v=dialog(self,"선택 영상 조건")
        f=QFormLayout();v.addLayout(f);session=QLineEdit(first["session_id"]);f.addRow("촬영 세션/날짜",session)
        count=QSpinBox();count.setRange(1,3);count.setValue(len(first["participating_chip_ids"]));f.addRow("참여 칩 수 (chip_1부터)",count)
        start=QSpinBox();start.setRange(0,100000000);start.setValue(first["interval"][0]);f.addRow("시작 프레임",start)
        end=QSpinBox();end.setRange(-1,100000000);end.setSpecialValueText("끝까지");end.setValue(first["interval"][1] if first["interval"][1] is not None else -1);f.addRow("끝 프레임",end)
        notes=QLineEdit(first.get("conditions",""));f.addRow("실험 조건",notes);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        p=copy.deepcopy(self.project)
        for exp in p["experiments"]:
            if exp["id"] in {e["id"] for e in selected}:exp.update(session_id=session.text().strip(),participating_chip_ids=list(COLORS)[:count.value()],interval=[start.value(),None if end.value()<0 else end.value()],conditions=notes.text())
        self.commit_settings(p)

    def build_profiles(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"설정")
        v.addWidget(label("촬영 조건과 측정 기준","title"));self.setup=SetupPanel(self);v.addWidget(self.setup,1)
        advanced=QGroupBox("고급 설정 · JSON (선택)");advanced.setCheckable(True);advanced.setChecked(False);v.addWidget(advanced)
        inner=QWidget();av=QVBoxLayout(inner);outer=QVBoxLayout(advanced);outer.addWidget(inner);inner.setVisible(False);advanced.toggled.connect(inner.setVisible)
        bar=QHBoxLayout();av.addLayout(bar);self.profile_kind=QComboBox()
        for name,key in [("시간 구간","time_profile"),("거리 보정","calibration"),("칩","chips"),("표식","templates"),("계측","analysis"),("물리 모델","physics"),("학습 분할","fit_split")]:self.profile_kind.addItem(name,key)
        bar.addWidget(self.profile_kind);self.profile_kind.currentIndexChanged.connect(self.load_profile)
        self.button(bar,"JSON 적용",self.apply_profile);self.button(bar,"JSON 불러오기",self.import_profile)
        self.profile_editor=QPlainTextEdit();self.profile_editor.setMaximumHeight(150);av.addWidget(self.profile_editor)
        self.profile_notes=QPlainTextEdit();self.profile_notes.setReadOnly(True);self.profile_notes.setVisible(False);av.addWidget(self.profile_notes)

    def commit_settings(self,p):
        if self.busy or self.batch and self.batch.thread and self.batch.thread.is_alive():
            raise ValueError("진행 중인 작업이 끝나거나 취소된 뒤 설정을 바꾸세요.")
        save_project(self.folder,p);self.project=p;self.refresh_queue();self.setup.refresh();self.load_profile();self.refresh_home()
        self.statusBar().showMessage("설정 저장 · 기존 결과는 보존됩니다. 변경된 설정으로 다시 분석하세요.")

    def apply_profile(self):
        super().apply_profile();self.setup.refresh();self.refresh_home()

    def load(self,folder):
        super().load(folder);self.setup.refresh();self.refresh_home()

    def job_update(self,value):
        super().job_update(value)
        stage=value.get("stage",value.get("status",""));frame=value.get("frame")
        self.queue_progress.setText(self.status_text(stage)+(f" · 프레임 {frame}" if frame is not None else ""))
        if stage=="batch_finished":
            if self.current_exp:
                exp=next((e for e in self.project["experiments"] if e["id"]==self.current_exp["id"]),None)
                if exp and exp.get("last_run"):self.current_exp=exp;self.current_run=self.folder/exp["last_run"];self.load_review_data();self.request_preview(self.current_frame)
            self.refresh_home()

    def build_review(self):
        super().build_review()
        page=self.tabs.widget(2);v=page.layout()
        old_tools=v.takeAt(0).layout()
        basic=QHBoxLayout();old_tools.removeWidget(self.chip_choice);old_tools.removeWidget(self.click_mode)
        basic.addWidget(self.chip_choice);basic.addWidget(self.click_mode)
        for text in ("실행 취소","다시 실행","보정 반영 재분석"):
            for i in range(old_tools.count()):
                item=old_tools.itemAt(i);w=item.widget()
                if isinstance(w,QPushButton) and w.text()==text:old_tools.removeWidget(w);basic.addWidget(w);break
        advanced=QGroupBox("표식 학습·ID·각도 도구");advanced.setCheckable(True);advanced.setChecked(False)
        box=QVBoxLayout(advanced);content=QWidget();content.setLayout(old_tools);box.addWidget(content);content.hide();advanced.toggled.connect(content.setVisible)
        v.insertLayout(0,basic);v.insertWidget(1,advanced)
        v.insertWidget(0,label("문제 프레임을 확인하고 근거를 남기세요","title"))
        v.insertWidget(1,label("← → 프레임 이동 · N/P 다음/이전 문제 · Ctrl+Z/Y 보정 취소/복원. 보정은 재분석하면 반영됩니다.","subtitle"))
        bar=QHBoxLayout();v.insertLayout(2,bar)
        self.button(bar,"이전 문제",lambda:self.jump_issue(-1));self.button(bar,"다음 문제",lambda:self.jump_issue(1)).setObjectName("primary")
        self.button(bar,"자동 측정이 맞는지 직접 확인…",self.label_frame);self.button(bar,"내가 표시한 위치와 비교",self.evaluate_truth)
        self.button(bar,"비교용 표시 수정 잠금",self.lock_truth)
        self.review_summary=label("");v.insertWidget(3,self.review_summary)
        # Long JSON remains available, collapsed by default.
        self.review_details.setVisible(False)
        check=QCheckBox("상세 수치/수정 로그 보기");check.toggled.connect(self.review_details.setVisible);v.addWidget(check)

    def load_review_data(self):
        super().load_review_data()
        # Recompute spacing on resize; v1's one-off tight_layout overlapped
        # labels when the review canvas became shorter than its initial size.
        self.figure.set_layout_engine("constrained")
        for ax in self.figure.axes:
            ax.yaxis.label.set_size(8);ax.tick_params(labelsize=8)
        if self.figure.axes and self.figure.axes[0].get_legend():
            self.figure.axes[0].legend(fontsize=7,ncols=3,loc="upper right")
        self.canvas.draw_idle()
        if hasattr(self,"review_summary"):
            text="영상 등록 목록에서 검토할 영상을 선택하세요."
            if self.current_run:
                q=read_json(self.current_run/"export/quality.json")
                text=f"선택 구간 관측 {(q.get('observed_fraction_selected_intervals',q['observed_fraction_all_target_frames']) or 0):.1%} · 검토 {q.get('review_frame_count','?')}프레임 · 충돌 {q['event_candidates']}건 · 정확도는 독립 라벨로 확인"
            self.review_summary.setText(text)

    def jump_issue(self,direction):
        if not self.current_run:raise ValueError("분석한 영상을 먼저 선택하세요.")
        q=read_json(self.current_run/"export/quality.json")
        frames=sorted({x["frame"] for x in q.get("review_issues",[])}|{e["closest_frame"] for e in self.events})
        if not frames:self.review_summary.setText("자동 검토 후보가 없습니다. 무작위 프레임도 확인하세요.");return
        options=[f for f in frames if (f-self.current_frame)*direction>0]
        target=(min(options) if direction>0 else max(options)) if options else (frames[0] if direction>0 else frames[-1])
        self.slider.setValue(target)

    def preview_ready(self,value):
        super().preview_ready(value)
        if value[0]!=self.preview_token:return
        if self.current_run:
            with Records(self.current_run/"records.sqlite") as db:
                timing=next(db.rows("frames",start=self.current_frame,end=self.current_frame),value[1])
        else:timing=value[1]
        def fmt(x):return "미확정" if x is None else f"{x:.6f} s"
        self.frame_label.setText(f"프레임 {self.current_frame} | 재생 {fmt(timing.get('presentation_time_s'))} | 실제 {fmt(timing.get('physical_time_s'))} | {timing.get('time_status','분석 전')}")

    def truth_path(self):
        if not self.current_run:raise ValueError("분석한 영상을 선택하세요.")
        return self.folder/"labels"/(self.current_exp["id"]+".json")

    def label_frame(self):
        path=self.truth_path();d,v=dialog(self,"원본을 보고 중심 위치 직접 표시")
        v.addWidget(label("현재 프레임을 직접 확인한 위치를 표시하세요. 화면에 보이는 칩을 모두 표시해야 개수까지 비교할 수 있습니다.\n자동 검출값은 미리 채우지 않습니다. 원본 영상의 픽셀 좌표를 사용합니다."))
        from .review_base import ImageView
        viewer=ImageView();viewer.set_image(self.original_image);v.addWidget(viewer,1)
        t=QTableWidget(len(self.current_exp["participating_chip_ids"]),5);t.setHorizontalHeaderLabels(["chip ID","중심 x px","중심 y px","반지름 px","각도 rad (선택)"]);v.addWidget(t)
        for i,k in enumerate(self.current_exp["participating_chip_ids"]):t.setItem(i,0,QTableWidgetItem(k))
        def click(x,y):
            row=max(0,t.currentRow());t.setItem(row,1,QTableWidgetItem(f"{x:.3f}"));t.setItem(row,2,QTableWidgetItem(f"{y:.3f}"))
        viewer.clicked.connect(click)
        v.addWidget(label("표의 칩 행을 선택하고 원본 중심을 클릭하세요. 반지름은 직접 입력합니다. 보이지 않는 칩 행의 좌표는 비워둡니다."))
        complete=QCheckBox("이 프레임의 모든 보이는 칩을 표시했습니다 (0개도 가능)");v.addWidget(complete);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        objects=[]
        for i in range(t.rowCount()):
            vals=[t.item(i,j).text().strip() if t.item(i,j) else "" for j in range(5)]
            if not any(vals[1:]):continue
            objects.append({"chip_id":vals[0],"center_px":[float(vals[1]),float(vals[2])],"radius_px":float(vals[3]),"angle_rad":float(vals[4]) if vals[4] else None})
        from ..analysis.benchmark import save_label
        save_label(path,self.current_frame,objects,read_json(self.current_run/"manifest.json")["source_hash"],complete.isChecked())
        self.review_summary.setText(f"프레임 {self.current_frame} 직접 표시한 위치 저장 · {len(objects)}개 칩")

    def evaluate_truth(self):
        from ..analysis.benchmark import evaluate_labels
        result=evaluate_labels(self.current_run,self.truth_path());self.refresh_home()
        def fmt(x,unit="") :return "미측정" if x is None else f"{x:.4f}{unit}"
        self.review_summary.setText(f"정답 {result['complete_frames']}프레임 · recall {fmt(result['recall'])} · precision {fmt(result['precision'])} · 중심 RMSE {fmt(result['center_rmse_px'],' px')} · 각도 MAE {fmt(result['angle_mae_deg'],'°')}")

    def lock_truth(self):
        from ..analysis.benchmark import lock_labels
        lock_labels(self.truth_path());self.review_summary.setText("비교용 위치 표시를 잠갔습니다. 이후에는 수정되지 않습니다.")

    def build_research(self):
        super().build_research();v=self.tabs.widget(3).layout()
        v.insertWidget(0,label("계수와 신뢰도를 함께 확인하세요","title"))
        self.fit_summary=label("단일 칩 자유운동 → 정상/접선 충돌 → 보류 세션 검증\n피팅할 데이터와 세션 분할을 먼저 지정하세요.");v.insertWidget(1,self.fit_summary)
        self.parameter_table=table(["계수","추정값","bootstrap 95% 구간","물리 상태","식별성"]);v.insertWidget(2,self.parameter_table)
        self.holdout_table=table(["보류 실험","평가 물리량","RMSE","MAE","95% 관측오차 내 비율"]);v.insertWidget(3,self.holdout_table)
        bar=QHBoxLayout();v.insertLayout(3,bar);self.button(bar,"계수 계산용 / 성능 확인용 실험 나누기",self.choose_split)
        self.button(bar,"접선 계수 민감도 스캔",self.scan_parameters)
        self.fit_editor.setVisible(False);self.fit_result.setVisible(False)
        self.bootstrap_count.setValue(0);self.bootstrap_count.setToolTip("0=빠른 점추정. 200회 이상은 시간 소요; 반복수 수렴과 세션 수를 확인하세요.")
        advanced=QCheckBox("고급 데이터셋 / 진단 JSON 보기");advanced.toggled.connect(self.fit_editor.setVisible);advanced.toggled.connect(self.fit_result.setVisible);v.addWidget(advanced)

    def open_fit_data(self):
        super().open_fit_data();self.update_fit_summary()

    def update_fit_summary(self):
        if not self.fit_editor.toPlainText().strip():return
        data=json.loads(self.fit_editor.toPlainText());split=data.get("split",{})
        self.fit_summary.setText(f"자유운동 {len(data.get('free_trials',[]))}개 · 충돌 {len(data.get('impact_trials',[]))}개\n학습: {', '.join(split.get('train',[])) or '미지정'} | 보류: {', '.join(split.get('holdout',[])) or '미지정'} | 최종시험: {', '.join(split.get('locked_test',[])) or '미지정'}")

    def make_fit_data(self):
        if not self.current_run:raise ValueError("관측 검토에서 완료 영상을 선택하세요.")
        d,v=dialog(self,"피팅에 넣을 관측 구간");f=QFormLayout();v.addLayout(f)
        kind=QComboBox();kind.addItems(["선택 칩 자유운동","승인한 고립 충돌 모두"]);f.addRow("자료 종류",kind)
        chip=QComboBox();chip.addItems(self.current_exp["participating_chip_ids"]);chip.setCurrentText(self.chip_choice.currentText());f.addRow("칩",chip)
        start=QSpinBox();start.setRange(0,self.slider.maximum());start.setValue(self.current_frame)
        end=QSpinBox();end.setRange(0,self.slider.maximum());end.setValue(self.slider.maximum());f.addRow("시작 프레임",start);f.addRow("끝 프레임",end);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        from ..models.research import free_trial,impact_trials
        dataset=json.loads(self.fit_editor.toPlainText()) if self.fit_editor.toPlainText().strip() else {"split":self.project["fit_split"],"seed":self.project["seed"],"free_trials":[],"impact_trials":[]}
        key="free_trials" if kind.currentIndex()==0 else "impact_trials"
        added=[free_trial(self.current_run,chip.currentText(),start.value(),end.value())] if kind.currentIndex()==0 else impact_trials(self.current_run)
        if not added:raise ValueError("피팅 가능한 승인 사건이 없습니다. 사건 검토와 각속도·물성을 확인하세요.")
        ids={x["id"] for x in dataset[key]}
        dataset[key].extend(x for x in added if x["id"] not in ids)
        self.fit_editor.setPlainText(json.dumps(dataset,ensure_ascii=False,indent=2));self.update_fit_summary()

    def choose_split(self):
        data=json.loads(self.fit_editor.toPlainText() or "{}")
        sessions=sorted({t["session_id"] for k in ("free_trials","impact_trials") for t in data.get(k,[])})
        if not sessions:raise ValueError("피팅 데이터를 먼저 추가하세요.")
        d,v=dialog(self,"세션 단위 분할");f=QFormLayout();v.addLayout(f);choices={}
        v.addWidget(label("보류는 모델 비교용, 최종시험은 피팅·모델선택에 사용하지 않는 세션입니다."))
        old=data.get("split",{})
        for s in sessions:
            c=QComboBox()
            for title,key in [("사용 안 함","unused"),("학습","train"),("보류 검증","holdout"),("잠긴 최종시험","locked_test")]:c.addItem(title,key)
            for key in ("train","holdout","locked_test"):
                if s in old.get(key,[]):c.setCurrentIndex(c.findData(key))
            f.addRow(s,c);choices[s]=c
        buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        data["split"]={"unit":"session",**{key:[s for s,c in choices.items() if c.currentData()==key] for key in ("train","holdout","locked_test")}}
        self.fit_editor.setPlainText(json.dumps(data,ensure_ascii=False,indent=2));self.project["fit_split"]=data["split"];self.save();self.update_fit_summary()

    def task_done(self,value):
        super().task_done(value)
        if self.last_fit:self.display_fit()
        self.refresh_home()

    def display_fit(self):
        self.parameter_table.setRowCount(0)
        self.holdout_table.setRowCount(0)
        for result in self.last_fit["stages"].values():
            for key,value in result["parameters"].items():
                i=self.parameter_table.rowCount();self.parameter_table.insertRow(i)
                ci=(result.get("bootstrap",{}).get("interval95") or {}).get(key)
                values=[key,f"{value:.7g}",f"[{ci[0]:.5g}, {ci[1]:.5g}]" if ci else "미계산",
                        result["physical_status"],result["diagnostics"]["identifiability"]]
                for j,x in enumerate(values):self.parameter_table.setItem(i,j,QTableWidgetItem(x))
            for trial in result.get("holdout",[]):
                for key,value in trial.items():
                    if isinstance(value,dict) and "rmse" in value:
                        i=self.holdout_table.rowCount();self.holdout_table.insertRow(i)
                        vals=[trial["trial_id"],key,value.get("rmse"),value.get("mae"),value.get("coverage95")]
                        for j,x in enumerate(vals):self.holdout_table.setItem(i,j,QTableWidgetItem(f"{x:.5g}" if isinstance(x,(float,int)) else str(x)))
        self.fit_summary.setText("피팅 완료 · 표의 물리 상태/식별성/CI를 함께 확인하세요.\n보류 오차는 결과 JSON에 저장됩니다. 계수 적용은 수치 성공·물리 허용·국소 식별을 모두 요구합니다.")

    def image_click(self,x,y):
        if self.click_mode.currentText()=="중심 보정 클릭" and not any(r["chip_id"]==self.chip_choice.currentText() for r in self.current_rows):
            if self.chip_choice.currentText() not in self.current_exp["participating_chip_ids"]:raise ValueError("참여 칩을 먼저 올바르게 지정하세요.")
            radius,ok=QInputDialog.getDouble(self,"누락된 칩 관측 추가","원본에서 읽은 반지름 (px)",30,3,2000,3)
            if not ok:return
            reason=self.reason()
            if reason:self.edit("insert_observation",{"point_px":[x,y],"radius_px":radius,"sigma_px":1.},reason)
            return
        super().image_click(x,y)

    def forward(self):
        if not self.current_run:raise ValueError("완료된 검토 영상을 선택하세요.")
        from ..models.research import compare_forward
        from PySide6.QtGui import QPixmap
        run=self.current_run;params=copy.deepcopy(self.project["physics"])
        def done(result):
            d,v=dialog(self,"실험과 Farkas → IFR → Farkas 전방 예측")
            v.addWidget(label("관측 초기상태에서 예측했습니다. 같은 실험으로 계수를 맞췄다면 독립 검증이 아닙니다."))
            for name,score in result["metrics"].items():v.addWidget(label(f"{name}: RMSE {score['rmse']:.6g} · MAE {score['mae']:.6g}"))
            path=run/"export/forward_comparison.png"
            if path.exists():
                picture=QLabel();picture.setPixmap(QPixmap(str(path)).scaledToWidth(720,Qt.TransformationMode.SmoothTransformation));v.addWidget(picture)
            buttons(d,v);d.exec()
        self.background(lambda:compare_forward(run,params),done,"전방 예측 비교")

    def apply_fit(self):
        if not self.last_fit:raise ValueError("피팅 결과가 없습니다.")
        for result in self.last_fit["stages"].values():
            if not result["diagnostics"]["optimizer_success"] or not result.get("normal_diagnostics",{"optimizer_success":True})["optimizer_success"]:
                raise ValueError("수치 최적화가 수렴하지 않았습니다.")
        super().apply_fit()
        impact_result=self.last_fit["stages"].get("impact_conditional")
        if impact_result:self.project["physics"]["model"]=impact_result["model"];self.save()
        self.setup.refresh();self.refresh_home()

    def scan_parameters(self):
        if not self.last_fit or "impact_conditional" not in self.last_fit["stages"]:raise ValueError("충돌 피팅을 먼저 실행하세요.")
        from ..models.inference import profile_impacts
        data=json.loads(self.fit_editor.toPlainText());fit=copy.deepcopy(self.last_fit["stages"]["impact_conditional"])
        from ..analysis.validation import split_trials
        trials,_=split_trials(data["impact_trials"],data["split"]["train"],data["split"]["holdout"],data["split"].get("unit","session"))
        def done(result):
            atomic_json(self.folder/"fits/impact_profile.json",result)
            self.fit_result.setPlainText(json.dumps(result,ensure_ascii=False,indent=2));self.fit_result.setVisible(True)
            self.fit_summary.setText("접선 robust 목적함수 profile 저장 완료 · 평평한 구간은 약한 식별성을 뜻합니다. 카이제곱 CI로 해석하지 마세요.")
        self.background(lambda:profile_impacts(trials,fit),done,"접선 계수별 nuisance 재최적화")

    def open_manual(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        path=Path(__file__).resolve().parents[3]/"docs/operations/README_V4_KO.md"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def main(folder=None):
    app=QApplication.instance() or QApplication([]);app.setApplicationName("PokerChip Research v2")
    window=MainWindow(folder);window.show();return app.exec()
