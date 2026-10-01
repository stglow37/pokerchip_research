"""Typed Korean setup forms; JSON is retained only as an advanced escape hatch."""
import copy
import json
import numpy as np
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,
    QDoubleSpinBox,QSpinBox,QLineEdit,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,
    QDialog,QDialogButtonBox,QPlainTextEdit,QCheckBox,QFileDialog,QGroupBox)
from ..core.storage import atomic_json,read_json


def number(lo,hi,decimals=3,value=0):
    w=QDoubleSpinBox();w.setRange(lo,hi);w.setDecimals(decimals);w.setValue(value);return w


def dialog(parent,title):
    d=QDialog(parent);d.setWindowTitle(title);d.resize(760,540);v=QVBoxLayout(d)
    return d,v


def buttons(d,v):
    b=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    b.accepted.connect(d.accept);b.rejected.connect(d.reject);v.addWidget(b)


class SetupPanel(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner
        layout=QVBoxLayout(self);tabs=QTabWidget();layout.addWidget(tabs);self.tabs=tabs
        p=QWidget();f=QFormLayout(p);tabs.addTab(p,"① 촬영 시간")
        hint=QLabel("삼성 FHD 240 fps · 전체 1/8배속\n재생 8초 = 실제 1초. 30fps 파일에서 실제 프레임 간격은 1/240초입니다.")
        hint.setWordWrap(True);f.addRow(hint)
        self.factor=number(.01,1000,4,8);f.addRow("재생시간 ÷ 배율",self.factor)
        self.capture=number(1,10000,2,240);f.addRow("촬영 fps (조건 기록)",self.capture)
        self.exposure=number(0,1000,4);self.exposure.setSpecialValueText("모름");f.addRow("노출시간 (실제 ms)",self.exposure)
        self.reference=QComboBox();self.reference.addItems(["unknown","start","midpoint","end"]);f.addRow("PTS에 대한 노출 기준",self.reference)
        self.readout=number(0,100,4);self.readout.setSpecialValueText("미측정")
        self.readout.hide()
        f.addRow(QLabel("롤링셔터 보정은 사용하지 않습니다."))
        self.time_note=QLabel();self.time_note.setWordWrap(True);f.addRow(self.time_note)
        b=QPushButton("촬영 조건 저장 (잠정 시간)");b.clicked.connect(lambda:owner.guarded(self.save_time));f.addRow(b)
        b=QPushButton("독립 시계 대응점으로 검증…");b.clicked.connect(lambda:owner.guarded(self.clock));f.addRow(b)
        p=QWidget();v=QVBoxLayout(p);tabs.addTab(p,"② 카메라·거리")
        self.geometry_note=QLabel();self.geometry_note.setWordWrap(True);v.addWidget(self.geometry_note)
        for text,cb in [("ChArUco 보정 영상 선택…",self.charuco),("평면 대응점·독립 검증점 입력…",self.plane),
                        ("보정 파일 불러오기…",self.import_calibration),("보정 파일 저장…",self.export_calibration)]:
            b=QPushButton(text);b.clicked.connect(lambda checked=False,cb=cb:owner.guarded(cb));v.addWidget(b)
        v.addWidget(QLabel("평면 표: 픽셀 y는 아래쪽, 실제 y는 위쪽입니다.\nfit 점 4개 이상과 따로 측정한 holdout 점을 입력하세요.\n렌즈 보정은 실험과 같은 줌·해상도·초점에서 촬영하세요."));v.addStretch()
        p=QWidget();v=QVBoxLayout(p);tabs.addTab(p,"③ 칩·계측")
        v.addWidget(QLabel("0 또는 빈 값은 미측정입니다. 명목 반지름과 실측값을 구분하세요."))
        self.chips=QTableWidget(3,6);self.chips.setHorizontalHeaderLabels(["ID","질량 g","반지름 mm","두께 mm","관성 kg·m² (빈칸=선택)","균질원판 근사 사용"])
        v.addWidget(self.chips)
        f=QFormLayout();v.addLayout(f)
        self.detector=QComboBox()
        self.detector.addItem("검정 칩 + 가장자리 색칠 + 내부 스티커","dark_chip")
        self.detector.setEnabled(False)
        f.addRow("검출 방식",self.detector)
        self.rmin=number(3,1000,1,20);self.rmax=number(4,2000,1,110)
        line=QHBoxLayout();line.addWidget(self.rmin);line.addWidget(QLabel("~"));line.addWidget(self.rmax);f.addRow("영상 반지름 범위 (px)",line)
        self.window=number(.001,10,4,.08);f.addRow("미분 창 길이 (실제 s)",self.window)
        self.omega=number(0,100000,2);self.omega.setSpecialValueText("미확정 → 각속도 차단");f.addRow("각속도 안전 상한 (rad/s)",self.omega)
        self.scale_sigma=number(0,100,4);f.addRow("공통 거리 상대 불확실성 (%)",self.scale_sigma)
        self.clock_sigma=number(0,100,4);f.addRow("공통 시간 상대 불확실성 (%)",self.clock_sigma)
        b=QPushButton("칩·계측 설정 저장");b.clicked.connect(lambda:owner.guarded(self.save_measurement));v.addWidget(b)
        p=QWidget();f=QFormLayout(p);tabs.addTab(p,"④ 이론 계수")
        f.addRow(QLabel("피팅 전 직접 입력하거나 피팅 결과를 적용할 수 있습니다. 빈칸은 미확정입니다.\n입력 e_t와 관측 접선 반발비 e_t_obs는 다릅니다."))
        self.physics_fields={}
        for title,key in [("바닥 마찰 μ_b ≥ 0","mu_bottom"),("법선 반발 e_n (0~1)","e_normal"),("접선 모델 e_t (-1~1)","e_tangential"),("충돌 마찰 μ_c ≥ 0","mu_collision")]:
            w=QLineEdit();w.setPlaceholderText("미확정");f.addRow(title,w);self.physics_fields[key]=w
        self.physics_model=QComboBox();self.physics_model.addItem("접촉속도 일관 재구성 (초기 회전 지원, 실험 검증 필요)","contact_consistent_reconstruction")
        self.physics_model.addItem("논문 percussion 범위 (초기 회전 0, 균질원판)","percussion_paper_scope");f.addRow("IFR 모델",self.physics_model)
        b=QPushButton("물리 계수 저장");b.clicked.connect(lambda:owner.guarded(self.save_physics));f.addRow(b)

    def refresh(self):
        if not self.owner.project:return
        p=self.owner.project;t=p["time_profile"];a=p["analysis"];c=p["calibration"]
        self.factor.setValue(t["segments"][0]["slow_factor"]);self.capture.setValue(t.get("capture_fps",240))
        self.exposure.setValue((t.get("exposure_s") or 0)*1000);self.reference.setCurrentText(t.get("exposure_reference","unknown"))
        self.readout.setValue((t.get("rolling_readout_s") or 0)*1000)
        self.time_note.setText(f"상태: {t['status']} · 구간 {len(t['segments'])}개\n여러 배속 구간은 고급 설정에서 구간별 입력. 단일 구간 저장은 이를 대체합니다.")
        validation=c.get("validation",{})
        details="\n".join(f"{'통과' if x['passed'] else '실패'} · {x['name']}: {x['value']} (기준 {x['limit']})" for x in validation.get("checks",[]))
        self.geometry_note.setText(f"보정 상태: {c.get('status')}\n{details}\n렌즈: {'입력됨' if c.get('K') else '미측정'} · 독립 측정 오차만 합격 판정에 사용합니다.")
        self.detector.setCurrentIndex(max(0,self.detector.findData(a.get("detector_profile","dark_chip"))))
        self.rmin.setValue(a["radius_px"][0]);self.rmax.setValue(a["radius_px"][1]);self.window.setValue(a["window_s"])
        self.omega.setValue(a.get("omega_bound_rad_s") or 0);self.scale_sigma.setValue(a.get("shared_scale_sigma_fraction",0)*100);self.clock_sigma.setValue(a.get("shared_clock_sigma_fraction",0)*100)
        self.chips.setRowCount(len(p["chips"]))
        for i,chip in enumerate(p["chips"]):
            values=[chip["id"],(chip.get("mass_kg") or 0)*1000,(chip.get("radius_m") or 0)*1000,(chip.get("thickness_m") or 0)*1000,chip.get("inertia_kg_m2") or ""]
            for j,value in enumerate(values):self.chips.setItem(i,j,QTableWidgetItem(str(value)))
            check=QCheckBox("I = ½mR²");check.setChecked(chip.get("inertia_model")=="uniform_disk");self.chips.setCellWidget(i,5,check)
        self.chips.resizeColumnsToContents()
        for key,w in self.physics_fields.items():w.setText("" if p["physics"].get(key) is None else str(p["physics"][key]))
        self.physics_model.setCurrentIndex(max(0,self.physics_model.findData(p["physics"]["model"])))

    def save_physics(self):
        self.owner.require();p=copy.deepcopy(self.owner.project)
        for key,w in self.physics_fields.items():
            text=w.text().strip();value=float(text) if text else None
            if value is not None:
                if not np.isfinite(value):raise ValueError("유한한 계수를 입력하세요.")
                if key=="e_normal" and not 0<=value<=1:raise ValueError("e_n은 0~1")
                if key=="e_tangential" and not -1<=value<=1:raise ValueError("e_t는 -1~1")
                if key.startswith("mu_") and value<0:raise ValueError("마찰계수는 0 이상")
            p["physics"][key]=value
        p["physics"]["model"]=self.physics_model.currentData();p["physics"].pop("fit_id",None)
        self.owner.commit_settings(p)

    def save_time(self):
        self.owner.require();p=copy.deepcopy(self.owner.project)
        p["time_profile"].update(status="declared",preset="samsung_fhd240_8x" if self.factor.value()==8 else "custom_declared",
            evidence=f"사용자 촬영조건: {self.capture.value()}fps, 재생 배율 {self.factor.value()}",capture_fps=self.capture.value(),
            segments=[{"p_start":0.,"p_end":None,"t_start":0.,"slow_factor":self.factor.value()}],
            exposure_s=self.exposure.value()/1000 or None,exposure_reference=self.reference.currentText(),
            rolling_readout_s=self.readout.value()/1000 or None)
        p["time_profile"].pop("clock_validation",None);self.owner.commit_settings(p)

    def clock(self):
        self.owner.require();d,v=dialog(self,"독립 시계 검증")
        v.addWidget(QLabel("영상 속 독립 타이머를 읽어 3개 이상 입력하세요.\n각 줄: 재생시각(s), 독립 타이머(s). 시작 시계 오프셋은 제거합니다.\n예시 숫자를 그대로 검증 근거로 사용하지 마세요."))
        editor=QPlainTextEdit();editor.setPlaceholderText("재생시각, 실제 타이머\n…");v.addWidget(editor)
        tolerance=number(.000001,1,6,.001);f=QFormLayout();f.addRow("허용오차 (s)",tolerance);v.addLayout(f)
        note=QLineEdit();note.setPlaceholderText("타이머 기기, 촬영 근거, 구간 등");v.addWidget(note);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        rows=[[float(x.strip()) for x in line.split(",")] for line in editor.toPlainText().splitlines() if line.strip()]
        if any(len(row)!=2 for row in rows) or not note.text().strip():raise ValueError("대응점 2열과 검증 근거를 입력하세요.")
        from ..core.timebase import verify_clock
        result=verify_clock(self.owner.project["time_profile"],[r[0] for r in rows],[r[1] for r in rows],tolerance.value())
        p=copy.deepcopy(self.owner.project);p["time_profile"].update(clock_validation=result,evidence=note.text(),status="verified" if result["passed"] else "declared")
        self.owner.commit_settings(p)

    def plane(self):
        self.owner.require();d,v=dialog(self,"평면 보정: fit / holdout 분리")
        v.addWidget(QLabel("실제 좌표는 mm 단위. fit 4개 이상, 독립 holdout 1개 이상.\n검토 영상의 '격자 대응점 클릭'으로 모은 점도 불러옵니다."))
        c=self.owner.project["calibration"];table=QTableWidget(max(10,len(c.get("pixel_points",[]))+3),5)
        table.setHorizontalHeaderLabels(["pixel x","pixel y","실제 x mm","실제 y mm","fit / holdout"]);v.addWidget(table)
        for i,(px,w) in enumerate(zip(c.get("pixel_points",[]),c.get("world_points",[]))):
            for j,x in enumerate([*px,*[k*1000 for k in w],"fit"]):table.setItem(i,j,QTableWidgetItem(str(x)))
        add=QPushButton("입력 행 추가");add.clicked.connect(lambda:table.setRowCount(table.rowCount()+5));v.addWidget(add)
        tolerance=number(.001,100,3,.5);f=QFormLayout();f.addRow("holdout RMSE 기준 (mm)",tolerance);v.addLayout(f)
        evidence=QLineEdit();evidence.setPlaceholderText("자/격자 실측 간격, 보정 근거");v.addWidget(evidence);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        fit=[];held=[]
        for i in range(table.rowCount()):
            values=[table.item(i,j).text().strip() if table.item(i,j) else "" for j in range(5)]
            if not any(values):continue
            if values[4] not in ("fit","holdout"):raise ValueError("점 종류는 fit 또는 holdout")
            row=[float(x) for x in values[:4]];(fit if values[4]=="fit" else held).append(row)
        from ..measurement.calibration import fit_plane
        base=copy.deepcopy(c);base.setdefault("validation_limits",{})["holdout_rmse_m"]=tolerance.value()/1000
        result=fit_plane([r[:2] for r in fit],[[x/1000 for x in r[2:]] for r in fit],base,
            {"pixel_points":[r[:2] for r in held],"world_points":[[x/1000 for x in r[2:]] for r in held]} if held else None,evidence=evidence.text())
        p=copy.deepcopy(self.owner.project);p["calibration"]=result;self.owner.commit_settings(p)

    def charuco(self):
        self.owner.require();file,_=QFileDialog.getOpenFileName(self,"같은 촬영 모드의 ChArUco 영상 선택")
        if not file:return
        d,v=dialog(self,"ChArUco 보드 규격");f=QFormLayout();v.addLayout(f)
        nx=QSpinBox();nx.setRange(3,40);nx.setValue(11);ny=QSpinBox();ny.setRange(3,40);ny.setValue(8)
        sq=number(.1,1000,3,15);marker=number(.1,1000,3,11);mode=QLineEdit("Samsung FHD240 slow8")
        for label,w in [("가로 칸",nx),("세로 칸",ny),("칸 길이 mm",sq),("마커 길이 mm",marker),("촬영 모드",mode)]:f.addRow(label,w)
        dictionary=QComboBox();dictionary.addItems(["DICT_4X4_50","DICT_5X5_100","DICT_6X6_250"]);f.addRow("마커 사전",dictionary);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        if marker.value()>=sq.value():raise ValueError("마커 길이는 칸보다 작아야 합니다.")
        spec={"squares":[nx.value(),ny.value()],"square_m":sq.value()/1000,"marker_m":marker.value()/1000,"dictionary":dictionary.currentText()}
        from ..measurement.calibration import charuco_video
        def done(result):
            p=copy.deepcopy(self.owner.project);p["calibration"]=result;self.owner.commit_settings(p)
        capture_mode=mode.text()
        self.owner.background(lambda:charuco_video(file,spec,capture_mode),done,"렌즈 보정 중 · 다음으로 평면 좌표를 입력하세요")

    def import_calibration(self):
        self.owner.require();file,_=QFileDialog.getOpenFileName(self,"보정 파일 선택","","JSON (*.json)")
        if not file:return
        p=copy.deepcopy(self.owner.project);c=read_json(file)
        from ..analysis.quality import calibration_gate
        if c.get("status")!="synthetic":
            c["validation"]=calibration_gate(c);c["status"]="verified" if c["validation"]["passed"] else "pending"
        p["calibration"]=c;self.owner.commit_settings(p)

    def export_calibration(self):
        self.owner.require();file,_=QFileDialog.getSaveFileName(self,"보정 저장","calibration.json","JSON (*.json)")
        if file:atomic_json(file,self.owner.project["calibration"])

    def save_measurement(self):
        self.owner.require();p=copy.deepcopy(self.owner.project)
        if self.rmin.value()>=self.rmax.value():raise ValueError("최소 반지름은 최대보다 작아야 합니다.")
        self.chips.setRowCount(len(p["chips"]))
        for i,chip in enumerate(p["chips"]):
            if self.chips.item(i,0).text()!=chip["id"]:raise ValueError("ID 변경 대신 검토 화면의 ID 교환을 사용하세요.")
            for j,key in [(1,"mass_kg"),(2,"radius_m"),(3,"thickness_m")]:
                value=float(self.chips.item(i,j).text() or 0)/1000;chip[key]=value or None
            raw=self.chips.item(i,4).text().strip();chip["inertia_kg_m2"]=float(raw) if raw else None
            chip["inertia_model"]="uniform_disk" if self.chips.cellWidget(i,5).isChecked() else "measured" if raw else "pending"
            chip["radius_status"]="user_entered_requires_measurement_record"
        p["analysis"].update(detector_profile=self.detector.currentData(),radius_px=[self.rmin.value(),self.rmax.value()],
            window_s=self.window.value(),omega_bound_rad_s=self.omega.value() or None,
            shared_scale_sigma_fraction=self.scale_sigma.value()/100,shared_clock_sigma_fraction=self.clock_sigma.value()/100)
        self.owner.commit_settings(p)
