"""Korean desktop workflow. Long work runs off the Qt event thread."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import threading
import traceback
import numpy as np
from PySide6.QtCore import Qt,Signal,QObject,QRectF
from PySide6.QtGui import QImage,QPainter,QColor,QDesktopServices,QFont,QFontDatabase
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QTabWidget,QPushButton,QLabel,
    QFileDialog,QMessageBox,QTableWidget,QTableWidgetItem,QPlainTextEdit,QComboBox,QSlider,QInputDialog,QSplitter,QDialog,QDialogButtonBox,QSpinBox)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from ..core.config import create_project,load_project,save_project,register,source_path,relink,COLORS
from ..core.storage import Records,read_json,atomic_json,dumps,digest,new_id,correction,undo_redo
from ..application.jobs import Batch
from ..measurement.video import frame_at,metadata


class Signals(QObject):
    job=Signal(object)
    completed=Signal(object)
    error=Signal(object)
    preview=Signal(object)


class ImageView(QWidget):
    clicked=Signal(float,float)
    def __init__(self):
        super().__init__();self.image=None;self.target=QRectF();self.setMinimumSize(420,280)
        self.zoom=1.;self.pan=np.zeros(2);self.drag_origin=None
        self.setToolTip("마우스 휠: 확대/축소 · 가운데 버튼 드래그: 이동 · 더블클릭: 전체 보기")

    def set_image(self,bgr):
        rgb=np.ascontiguousarray(bgr[:,:,::-1]);h,w=rgb.shape[:2]
        self.image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy();self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor("#152331"))
        if self.image is None:
            painter.setPen(Qt.GlobalColor.white);painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,"영상을 선택하면 원본 프레임을 표시합니다.");return
        scale=min(self.width()/self.image.width(),self.height()/self.image.height())*self.zoom
        w,h=self.image.width()*scale,self.image.height()*scale
        self.target=QRectF((self.width()-w)/2+self.pan[0],(self.height()-h)/2+self.pan[1],w,h)
        painter.drawImage(self.target,self.image)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:
            self.drag_origin=np.array([event.position().x(),event.position().y()]);return
        if self.image is not None and self.target.contains(event.position()):
            self.clicked.emit((event.position().x()-self.target.x())*self.image.width()/self.target.width(),
                              (event.position().y()-self.target.y())*self.image.height()/self.target.height())

    def mouseMoveEvent(self,event):
        if self.drag_origin is not None:
            point=np.array([event.position().x(),event.position().y()]);self.pan+=point-self.drag_origin;self.drag_origin=point;self.update()

    def mouseReleaseEvent(self,event):self.drag_origin=None

    def wheelEvent(self,event):
        self.zoom=float(np.clip(self.zoom*(1.2 if event.angleDelta().y()>0 else 1/1.2),1,12));self.update();event.accept()

    def mouseDoubleClickEvent(self,event):self.zoom=1.;self.pan[:]=0;self.update()


from .viewer import ImageView, FrameLoader


class MainWindow(QMainWindow):
    def __init__(self,folder=None):
        super().__init__();self.setWindowTitle("포커칩 연구실 · 관측과 물리 예측");self.resize(1320,900)
        # Offscreen Qt and some clean Windows profiles lack automatic CJK fallback.
        import os
        font_path=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts/malgun.ttf"
        if font_path.exists():QFontDatabase.addApplicationFont(str(font_path))
        QApplication.instance().setFont(QFont("Malgun Gothic",9))
        self.folder=None;self.project=None;self.batch=None;self.busy=False;self.active_job=None;self.current_exp=None;self.current_run=None
        self.current_frame=0;self.original_image=None;self.current_rows=[];self.preview_token=0;self.marker_seeds={};self.template_samples={}
        self.signals=Signals();self.signals.error.connect(self.task_failed);self.signals.completed.connect(self.task_done)
        self.signals.job.connect(self.job_update);self.signals.preview.connect(self.preview_ready)
        central=QWidget();self.setCentralWidget(central);layout=QVBoxLayout(central)
        top=QHBoxLayout();layout.addLayout(top)
        for label,callback in [("새 프로젝트",self.new_project),("프로젝트 열기",self.open_project),("합성 데모 만들기",self.demo_project),("저장",self.save)]:self.button(top,label,callback)
        self.project_label=QLabel("프로젝트를 생성하거나 여세요.");top.addWidget(self.project_label,1)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.build_queue();self.build_profiles();self.build_review();self.build_research();self.build_export()
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(100);layout.addWidget(self.log)
        self.setAcceptDrops(True)
        self.statusBar().showMessage("준비 · 실험 미검증 값을 임의로 채우지 마세요.")
        if folder:self.load(folder)

    def button(self,layout,label,callback):
        button=QPushButton(label);button.clicked.connect(lambda checked=False:self.guarded(callback));layout.addWidget(button);return button

    def guarded(self,callback):
        try:return callback()
        except Exception as exc:self.show_error(f"{type(exc).__name__}: {exc}")

    def show_error(self,text):
        self.log.appendPlainText(text);self.statusBar().showMessage("오류 · 상세 로그 확인")
        QMessageBox.warning(self,"작업 확인",text)

    def error(self,text):
        """A background-task failure, not a validation/preview message."""
        self.busy=False;self.active_job=None;self.show_error(text)

    def require(self):
        if self.project is None:raise ValueError("먼저 프로젝트를 여세요.")

    def save(self):
        self.require();save_project(self.folder,self.project);self.project_label.setText(f"{self.project['name']} | {self.project['mode']}");self.project_label.setToolTip(str(self.folder))

    def load(self,folder):
        if self.busy:raise ValueError("진행 중인 작업이 끝난 뒤 프로젝트를 바꾸세요.")
        if self.batch and self.batch.thread and self.batch.thread.is_alive():raise ValueError("진행 중 batch를 취소하고 완료를 기다리세요.")
        self.folder=Path(folder);self.project=load_project(folder);self.save();self.refresh_queue();self.load_profile()

    def new_project(self):
        if self.busy:raise ValueError("진행 중인 작업이 끝난 뒤 새 프로젝트를 만드세요.")
        folder=QFileDialog.getExistingDirectory(self,"새 프로젝트를 저장할 빈 폴더")
        if folder:create_project(folder);self.load(folder)

    def open_project(self):
        if self.busy:raise ValueError("진행 중인 작업이 끝난 뒤 프로젝트를 바꾸세요.")
        file,_=QFileDialog.getOpenFileName(self,"project.json 선택","","프로젝트 (project.json)")
        if file:self.load(Path(file).parent)

    def demo_project(self):
        folder=QFileDialog.getExistingDirectory(self,"합성 데모를 만들 빈 폴더")
        if folder:
            from ..application.demo import make_demo
            self.background(lambda:make_demo(folder),lambda result:self.load(folder),"합성 데모 생성")

    def background(self,work,done=None,label="작업",allow_project_updates=False):
        if self.busy or self.batch and self.batch.thread and self.batch.thread.is_alive():raise ValueError("현재 작업이 끝난 후 실행하세요.")
        context={"id":new_id("job"),"project_id":self.project.get("id") if self.project else None,
                 "folder":str(self.folder.resolve()) if self.folder else None,
                 "settings_hash":digest(self.project) if self.project else None,
                 "allow_project_updates":allow_project_updates,"label":label}
        self.active_job=context;self.busy=True;self.statusBar().showMessage(label)
        def worker():
            try:self.signals.completed.emit((context,done,work()))
            except Exception as exc:self.signals.error.emit((context,f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))
        threading.Thread(target=worker,daemon=True).start()

    def task_done(self,value):
        context,done,result=value
        if not self.active_job or context["id"]!=self.active_job["id"]:return
        self.busy=False;self.active_job=None
        current_id=self.project.get("id") if self.project else None
        current_folder=str(self.folder.resolve()) if self.folder else None
        if context["project_id"]!=current_id or context["folder"]!=current_folder:
            self.show_error("완료된 작업의 프로젝트가 현재 열린 프로젝트와 달라 결과 연결을 중단했습니다.")
            return
        if self.project and not context["allow_project_updates"] and digest(self.project)!=context["settings_hash"]:
            self.show_error("작업 중 프로젝트 설정이 바뀌어 계산 결과를 현재 프로젝트에 연결하지 않았습니다. 변경 전 설정으로 다시 실행하세요.")
            return
        if done:self.guarded(lambda:done(result))
        self.statusBar().showMessage("작업 완료 · 품질 합격 여부는 결과에서 별도 확인")

    def task_failed(self,value):
        context,text=value if isinstance(value,tuple) else (self.active_job,value)
        if context and self.active_job and context.get("id")!=self.active_job.get("id"):return
        self.active_job=None
        self.error(text)

    def build_queue(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"1 · 영상 등록 / 작업")
        bar=QHBoxLayout();v.addLayout(bar)
        for label,cb in [("영상 여러 개 등록",self.add_videos),("선택 조건 수정",self.edit_experiments),("원본 재연결",self.reconnect),("모두 분석 / 재개",self.start_batch),("선택 분석 / 재시도",lambda:self.start_batch(True)),("일시정지",lambda:self.batch.pause() if self.batch else None),("계속",lambda:self.batch.resume() if self.batch else None),("취소",lambda:self.batch.cancel() if self.batch else None)]:self.button(bar,label,cb)
        v.addWidget(QLabel("50개 이상 파일 선택·끌어놓기 가능 · 기본 1 worker · 실패 파일 격리 · 취소는 프레임/단계 경계에서 반영"))
        self.drop_kind=QComboBox();self.drop_kind.addItems(["끌어놓기: 실험 영상","끌어놓기: ChArUco 보정 영상"]);v.addWidget(self.drop_kind)
        self.queue_table=QTableWidget(0,6);self.queue_table.setHorizontalHeaderLabels(["이름","세션","참여 칩","분석 구간","상태","experiment ID"])
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.cellDoubleClicked.connect(lambda row,col:self.guarded(lambda:self.select_experiment(row)))
        v.addWidget(self.queue_table)
        self.button(v,"선택 영상 검토",lambda:self.select_experiment(self.queue_table.currentRow()))

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()

    def dropEvent(self,event):
        paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if self.drop_kind.currentIndex()==1:
            if paths:self.guarded(lambda:self.calibrate(paths[0]))
        else:self.guarded(lambda:self.add_paths(paths))
        event.acceptProposedAction()

    def add_paths(self,paths):
        self.require();register(self.folder,self.project,paths);self.refresh_queue()

    def add_videos(self):
        files,_=QFileDialog.getOpenFileNames(self,"실험 영상 등록 (원본은 복사·변경하지 않음)","","영상 (*.mp4 *.mov *.mkv *.avi);;모든 파일 (*)")
        if files:self.add_paths(files)

    def refresh_queue(self):
        if self.project is None:return
        self.queue_table.setRowCount(len(self.project["experiments"]))
        for i,e in enumerate(self.project["experiments"]):
            for j,value in enumerate([e["name"],e["session_id"],", ".join(e["participating_chip_ids"]),str(e["interval"]),e.get("status","pending"),e["id"]]):self.queue_table.setItem(i,j,QTableWidgetItem(value))
        self.queue_table.resizeColumnsToContents()

    def selected_experiments(self):
        self.require();rows=sorted({index.row() for index in self.queue_table.selectedIndexes()})
        if not rows:raise ValueError("영상을 선택하세요.")
        return [self.project["experiments"][i] for i in rows]

    def edit_experiments(self):
        selected=self.selected_experiments();first=selected[0]
        keys=("session_id","participating_chip_ids","interval","conditions","excluded_frame_intervals")
        value=self.json_dialog("선택 영상 조건 일괄 수정",{k:first.get(k,[]) if k=="excluded_frame_intervals" else first.get(k) for k in keys})
        if value is not None:
            for e in selected:e.update(copy.deepcopy(value))
            self.save();self.refresh_queue()

    def reconnect(self):
        exp=self.selected_experiments()[0];file,_=QFileDialog.getOpenFileName(self,"이동한 동일 원본 선택")
        if file:relink(self.folder,self.project,exp["id"],file);self.refresh_queue()

    def start_batch(self,selected=False):
        self.require()
        if self.busy or self.batch and self.batch.thread and self.batch.thread.is_alive():raise ValueError("작업이 이미 실행 중입니다.")
        ids=[e["id"] for e in self.selected_experiments()] if selected else None
        self.save();self.batch=Batch(self.folder,self.project,self.signals.job.emit);self.batch.start(ids)

    def job_update(self,value):
        self.log.appendPlainText(dumps(value))
        if value.get("experiment_id"):
            exp=next(e for e in self.project["experiments"] if e["id"]==value["experiment_id"])
            exp["status"]=value.get("status",value.get("stage","running"))
            if value.get("run"):exp["last_run"]=str(Path(value["run"]).relative_to(self.folder))
            if value.get("source_hash"):exp["source_hash"]=value["source_hash"]
            self.refresh_queue()
        if value.get("stage")=="batch_finished":self.save();self.statusBar().showMessage("배치 종료 · 실패/검토 필요 상태를 확인하세요.")

    def build_profiles(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"2 · 시간 / 보정 / 표식")
        bar=QHBoxLayout();v.addLayout(bar);self.profile_kind=QComboBox()
        for label,key in [("시간축과 독립 근거","time_profile"),("카메라 / 평면 / 높이","calibration"),("칩 실측 규격","chips"),("두 표식 template","templates"),("계측·회전 alias 상한","analysis"),("물리 계수·모델","physics"),("학습 / 보류 세션","fit_split")]:self.profile_kind.addItem(label,key)
        self.profile_kind.currentIndexChanged.connect(self.load_profile);bar.addWidget(self.profile_kind)
        for label,cb in [("적용·저장",self.apply_profile),("JSON 불러오기",self.import_profile),("JSON 저장",self.export_profile)]:self.button(bar,label,cb)
        v.addWidget(QLabel("미실측값은 null 유지 · 시간 verified에는 독립 근거 필수 · 수정한 설정은 다음 run에 적용 · 세부 필드는 데이터 사전 참조"))
        self.profile_editor=QPlainTextEdit();v.addWidget(self.profile_editor,1)
        bar=QHBoxLayout();v.addLayout(bar)
        for label,cb in [("시간 PTS 검사",self.inspect_timing),("ChArUco 영상 보정",self.calibrate),("격자 대응점 → 평면 보정",self.plane_dialog),("현재 프레임 격자 검출",self.find_grid)]:self.button(bar,label,cb)
        self.profile_notes=QPlainTextEdit();self.profile_notes.setReadOnly(True);self.profile_notes.setMaximumHeight(140);v.addWidget(self.profile_notes)

    def load_profile(self):
        if self.project is None:return
        self.profile_editor.setPlainText(json.dumps(self.project[self.profile_kind.currentData()],ensure_ascii=False,indent=2))

    def apply_profile(self):
        self.require();new=copy.deepcopy(self.project);new[self.profile_kind.currentData()]=json.loads(self.profile_editor.toPlainText())
        save_project(self.folder,new);self.project=new;self.save();self.profile_notes.setPlainText("설정 저장 완료. 기존 run은 보존합니다. 새 분석을 실행하세요.")

    def import_profile(self):
        file,_=QFileDialog.getOpenFileName(self,"profile JSON 선택","","JSON (*.json)")
        if file:self.profile_editor.setPlainText(json.dumps(read_json(file),ensure_ascii=False,indent=2))

    def export_profile(self):
        file,_=QFileDialog.getSaveFileName(self,"profile 저장","profile.json","JSON (*.json)")
        if file:atomic_json(file,json.loads(self.profile_editor.toPlainText()))

    def json_dialog(self,title,value):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(760,580);v=QVBoxLayout(dialog)
        text=QPlainTextEdit();text.setPlainText(json.dumps(value,ensure_ascii=False,indent=2));v.addWidget(text)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);v.addWidget(buttons)
        return json.loads(text.toPlainText()) if dialog.exec()==QDialog.DialogCode.Accepted else None

    def inspect_timing(self):
        self.require();exp=self.current_exp or self.selected_experiments()[0];path=source_path(self.folder,exp)
        def work():
            from ..measurement.video import frames
            from ..application.exporting import table_csv,FIELDS
            out=self.folder/"intake"/exp["id"];out.mkdir(parents=True,exist_ok=True)
            table_csv(out/"timing.csv",FIELDS["frames"],(t for t,_ in frames(path)))
            data=metadata(path);atomic_json(out/"metadata.json",data);return data
        self.background(work,lambda result:self.profile_notes.setPlainText(json.dumps(result,ensure_ascii=False,indent=2)),"PTS 전체 검사")

    def calibrate(self,file=None):
        self.require()
        if file is None:file,_=QFileDialog.getOpenFileName(self,"ChArUco 보정 원본 영상")
        if not file:return
        spec=self.json_dialog("보드 실측 규격과 촬영 모드",{"squares":[8,6],"square_m":None,"marker_m":None,"dictionary":"DICT_4X4_50","capture_mode":"직접 입력"})
        if spec is None:return
        if not spec.get("square_m") or not spec.get("marker_m"):raise ValueError("보드 실측 길이를 입력하세요.")
        from ..measurement.calibration import charuco_video
        def done(result):
            self.project["calibration"]=result;self.save();self.load_profile();self.profile_notes.setPlainText(json.dumps({k:v for k,v in result.items() if k not in ("observations",)},ensure_ascii=False,indent=2))
        self.background(lambda:charuco_video(file,spec,spec["capture_mode"]),done,"ChArUco 학습·holdout")

    def plane_dialog(self):
        self.require()
        data=self.json_dialog("평면 대응점: pixel y 아래, world y 위 / holdout은 별도 점",{"pixel_points":self.project["calibration"].get("pixel_points",[]),"world_points":self.project["calibration"].get("world_points",[]),"holdout":None,"independent_lengths":[],"evidence":""})
        if data is None:return
        from ..measurement.calibration import fit_plane
        self.project["calibration"]=fit_plane(data["pixel_points"],data["world_points"],self.project["calibration"],data.get("holdout"),data.get("independent_lengths"),data["evidence"])
        self.save();self.load_profile()

    def find_grid(self):
        if self.original_image is None:raise ValueError("검토 탭에서 기준 프레임을 선택하세요.")
        spec=self.json_dialog("격자 내부 교차점 수와 실측 간격",{"columns":9,"rows":7,"spacing_x_m":None,"spacing_y_m":None})
        if spec is None:return
        if not spec.get("spacing_x_m") or not spec.get("spacing_y_m"):raise ValueError("x/y 격자 간격 실측 필요")
        from ..measurement.calibration import grid_points
        points=grid_points(self.original_image,(spec["columns"],spec["rows"]))
        if len(points)==0:raise ValueError("규칙 격자 검출 실패. 클릭 대응점을 입력하세요.")
        world=[[x*spec["spacing_x_m"],-y*spec["spacing_y_m"]] for y in range(spec["rows"]) for x in range(spec["columns"])]
        self.project["calibration"]["pixel_points"]=points.tolist();self.project["calibration"]["world_points"]=world
        self.save();self.plane_dialog()

    def build_review(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"3 · 영상 / 사건 검토")
        bar=QHBoxLayout();v.addLayout(bar)
        self.chip_choice=QComboBox();self.chip_choice.addItems(list(COLORS));bar.addWidget(self.chip_choice)
        self.click_mode=QComboBox();self.click_mode.addItems(["확대·조회","중심 보정 클릭","가장자리 색 표시 클릭","안쪽 스티커 클릭","격자 대응점 클릭"]);bar.addWidget(self.click_mode)
        for label,cb in [("표식 학습 저장",self.save_template),("경계 호 재적합",self.refit_arc),("ID 구간 교환",self.swap_ids),("각도 보정",self.correct_angle),("실행 취소",lambda:self.history(-1)),("다시 실행",lambda:self.history(1)),("보정 반영 재분석",lambda:self.start_current())]:self.button(bar,label,cb)
        options=QHBoxLayout();v.addLayout(options)
        self.button(options,"선명한 표식 기준 프레임 제안",self.suggest_template_frame)
        self.graph_kind=QComboBox();self.graph_kind.addItems(["위치 / 각도 / 각속도","칩 쌍 거리 / 측정 품질"]);options.addWidget(self.graph_kind)
        self.graph_kind.currentIndexChanged.connect(self.load_review_data)
        split=QSplitter();v.addWidget(split,1);left=QWidget();lv=QVBoxLayout(left);split.addWidget(left)
        self.image_view=ImageView();self.image_view.clicked.connect(lambda x,y:self.guarded(lambda:self.image_click(x,y)));lv.addWidget(self.image_view,1)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,0);self.slider.valueChanged.connect(self.request_preview);lv.addWidget(self.slider)
        self.frame_label=QLabel("frame / physical time");lv.addWidget(self.frame_label)
        right=QWidget();rv=QVBoxLayout(right);split.addWidget(right)
        self.figure=Figure(figsize=(5,4));self.canvas=FigureCanvasQTAgg(self.figure);rv.addWidget(self.canvas,1)
        self.event_table=QTableWidget(0,4);self.event_table.setHorizontalHeaderLabels(["사건","종류","프레임 구간","상태"]);self.event_table.setMaximumHeight(190)
        self.event_table.cellClicked.connect(lambda row,col:self.event_selected(row));rv.addWidget(self.event_table)
        buttons=QHBoxLayout();rv.addLayout(buttons)
        self.button(buttons,"사건 승인",lambda:self.review_event(True));self.button(buttons,"사건 제외 / 종류",lambda:self.review_event(False))
        self.review_details=QPlainTextEdit();self.review_details.setReadOnly(True);self.review_details.setMaximumHeight(130);v.addWidget(self.review_details)

    def select_experiment(self,index):
        self.require()
        if index<0:raise ValueError("영상을 선택하세요.")
        self.current_exp=self.project["experiments"][index];self.current_run=self.folder/self.current_exp["last_run"] if self.current_exp.get("last_run") else None
        path=source_path(self.folder,self.current_exp);meta=metadata(path)
        maximum=max(0,meta.get("estimated_frames",0)-1)
        if self.current_run:
            with Records(self.current_run/"records.sqlite") as db:
                result=db.db.execute("SELECT MAX(frame) FROM frames").fetchone()[0]
                if result is not None:maximum=max(maximum,result)
        self.slider.setRange(0,maximum);self.tabs.setCurrentIndex(2);self.load_review_data();self.request_preview(self.slider.value())

    def load_review_data(self):
        quality=self.graph_kind.currentIndex()==1
        self.figure.clear();axes=self.figure.subplots(2 if quality else 3,1);self.events=[]
        if self.current_run:
            with Records(self.current_run/"records.sqlite") as db:
                stride=max(1,db.count("trajectories")//3000)
                rows=[r for i,r in enumerate(db.rows("trajectories")) if i%stride==0];self.events=list(db.rows("events"))
            keys=sorted({r["chip_id"] for r in rows});self.chip_choice.clear();self.chip_choice.addItems(sorted(set(keys)|set(self.current_exp["participating_chip_ids"])))
            for chip in ([] if quality else keys):
                selected=[r for r in rows if r["chip_id"]==chip];f=[r["frame_index"] for r in selected]
                axes[0].plot(f,[r["raw_center_px"][0] for r in selected],label=chip)
                axes[1].plot(f,[r.get("theta_wrapped_rad") if r.get("theta_wrapped_rad") is not None else np.nan for r in selected])
                axes[2].plot(f,[r.get("omega_rad_s") if r.get("omega_rad_s") is not None else np.nan for r in selected])
            if keys:axes[0].legend(fontsize=7)
            if quality:
                from itertools import combinations
                groups={}
                for r in rows:groups.setdefault(r["frame_index"],{})[r["chip_id"]]=r
                for a,b in combinations(keys,2):
                    samples=[(f,np.linalg.norm(np.array(g[a]["raw_center_px"])-g[b]["raw_center_px"])) for f,g in groups.items() if a in g and b in g]
                    if samples:axes[0].plot(*np.array(samples).T,label=a+" / "+b)
                with Records(self.current_run/"records.sqlite") as db:
                    fs=list(db.rows("frames")) if db.count("frames")<3000 else [r for i,r in enumerate(db.rows("frames")) if i%max(1,db.count("frames")//3000)==0]
                axes[1].plot([r["frame_index"] for r in fs],[r.get("blur_score",0) for r in fs])
                if axes[0].lines:axes[0].legend(fontsize=7)
        for ax,label in zip(axes,["distance (px)","sharpness"] if quality else ["x (px)","theta (rad)","omega (rad/s)"]):ax.set_ylabel(label);ax.grid(alpha=.25)
        axes[-1].set_xlabel("frame");self.figure.tight_layout();self.cursor_lines=[a.axvline(self.current_frame,color="red",alpha=.5) for a in axes];self.canvas.draw_idle()
        self.event_table.setRowCount(len(self.events))
        for i,e in enumerate(self.events):
            for j,value in enumerate([e["id"],e["kind"],f"{e['frame_start']}–{e['frame_end']}",e["status"]]):self.event_table.setItem(i,j,QTableWidgetItem(value))

    def suggest_template_frame(self):
        if not self.current_run:raise ValueError("분석 후 검토 영상을 선택하세요.")
        with Records(self.current_run/"records.sqlite") as db:
            best=max(db.rows("frames"),key=lambda r:r.get("blur_score",0)*(1-r.get("clipped_fraction",0)),default=None)
        if best is None:raise ValueError("프레임 품질 기록이 없습니다.")
        self.slider.setValue(best["frame_index"])
        self.log.appendPlainText("선명도 기반 후보입니다. 가림·두 표식·고유 ID를 직접 확인하고 클릭하여 학습하세요.")

    def request_preview(self,frame):
        if self.current_exp is None:return
        self.marker_seeds={}
        self.current_frame=frame;self.preview_token+=1;token=self.preview_token;path=source_path(self.folder,self.current_exp)
        if not hasattr(self,'frame_loader'):
            self.frame_loader=FrameLoader(self)
            self.frame_loader.ready.connect(self.preview_ready)
            self.frame_loader.failed.connect(self.preview_failed)
        self.frame_loader.submit(token,path,frame)

    def preview_failed(self,value):
        token,message=value
        if token!=self.preview_token:return
        self.log.appendPlainText("프리뷰 오류: "+message)
        self.statusBar().showMessage("현재 프레임을 불러오지 못했습니다. 다른 프레임 또는 원본을 확인하세요.")

    def preview_ready(self,value):
        token,timing,image=value
        if token!=self.preview_token:return
        import cv2
        self.original_image=image.copy();self.current_rows=[]
        if self.current_run:
            with Records(self.current_run/"records.sqlite") as db:
                self.current_rows=list(db.rows("manual",start=self.current_frame,end=self.current_frame))
                timing=next(db.rows("frames",start=self.current_frame,end=self.current_frame),timing)
            for row in self.current_rows:
                center=tuple(np.round(row["raw_center_px"]).astype(int));r=int(row["radius_px"])
                cv2.circle(image,center,r,(40,200,40),2);cv2.putText(image,row["chip_id"],(center[0]-r,center[1]-r),cv2.FONT_HERSHEY_SIMPLEX,.5,(40,200,40),1)
        self.image_view.set_image(image);self.frame_label.setText(f"프레임 {self.current_frame} | 재생 {timing.get('presentation_time_s')} s | 물리 {timing.get('physical_time_s')} s")
        self.review_details.setPlainText(json.dumps({"timing":timing,"observations":[{k:v for k,v in r.items() if k not in ("edge_points_px","markers")} for r in self.current_rows]},ensure_ascii=False,indent=2))
        for line in getattr(self,"cursor_lines",[]):line.set_xdata([self.current_frame,self.current_frame])
        self.canvas.draw_idle()

    def selected_row(self):
        row=next((r for r in self.current_rows if r["chip_id"]==self.chip_choice.currentText()),None)
        if row is None:raise ValueError("선택 칩의 현재 관측이 없습니다. 먼저 다른 프레임 또는 ID를 선택하세요.")
        return row

    def reason(self):
        text,ok=QInputDialog.getText(self,"수정 근거","원본 영상에서 확인한 수정 이유:")
        if not ok:return None
        if not text.strip():raise ValueError("수정 이유가 필요합니다.")
        return text

    def edit(self,action,after,reason,frames=None,chip=None,event_id=None):
        target={"experiment_id":self.current_exp["id"],"frames":frames or [self.current_frame,self.current_frame],"chip_id":chip or self.chip_choice.currentText()}
        if event_id:target["event_id"]=event_id
        correction(self.project,action,target,after,reason,before=self.current_rows);self.save()
        self.log.appendPlainText("보정 이력 저장. 새 분석을 실행하면 파생 결과가 갱신됩니다.")

    def image_click(self,x,y):
        mode=self.click_mode.currentText()
        if mode=="확대·조회":
            self.review_details.appendPlainText(f"pixel ({x:.3f}, {y:.3f})");return
        if mode=="중심 보정 클릭":
            self.selected_row();reason=self.reason()
            if reason:self.edit("center",{"point_px":[x,y],"sigma_px":1.},reason)
        elif mode in ("가장자리 색 표시 클릭","안쪽 스티커 클릭"):
            self.selected_row();self.marker_seeds["rim" if mode.startswith("가장자리") else "inner"]=[x,y]
            self.review_details.appendPlainText(f"{mode}: {x:.2f}, {y:.2f}")
        elif mode=="격자 대응점 클릭":
            text,ok=QInputDialog.getText(self,"격자 world 좌표","x_m, y_m (y 위쪽):")
            if ok:
                point=[float(v.strip()) for v in text.split(",")]
                if len(point)!=2:raise ValueError("x,y 두 값 필요")
                self.project["calibration"].setdefault("pixel_points",[]).append([x,y]);self.project["calibration"].setdefault("world_points",[]).append(point);self.save()

    def save_template(self):
        row=self.selected_row();chip=self.chip_choice.currentText()
        if chip not in {c["id"] for c in self.project["chips"]}:raise ValueError("고정 칩 ID를 먼저 지정하세요.")
        if set(self.marker_seeds)!={"rim","inner"}:raise ValueError("같은 프레임에서 rim과 inner를 각각 클릭하세요.")
        from ..measurement.vision import learn_template,learn_color
        from ..measurement.calibration import to_world
        sample={};colors={};center=np.array(row["raw_center_px"])
        height=next((c.get("thickness_m") for c in self.project["chips"] if c["id"]==chip),None)
        for role,p in self.marker_seeds.items():
            wp=to_world([center,p],self.project["calibration"],height)
            v=wp[1]-wp[0] if wp is not None else (np.array(p)-center)*[1,-1]
            ratio=np.linalg.norm(v)/row["radius_m"] if wp is not None and row.get("radius_m") else np.linalg.norm(np.array(p)-center)/row["radius_px"]
            sample[role]={"angle":float(np.arctan2(v[1],v[0])),"radius_ratio":float(ratio)}
            colors[role]=learn_color(self.original_image,p)
        self.template_samples.setdefault(chip,[]).append(sample)
        template=learn_template(self.template_samples[chip],self.current_exp["session_id"],colors)
        old=self.project["templates"].get(chip)
        template["version"]=(old or {}).get("version",0)+1
        self.project["templates"][chip]=template;self.project.setdefault("template_history",[]).append({"chip_id":chip,"before":old,"after":template})
        self.marker_seeds={};self.save();self.load_profile();self.review_details.appendPlainText("표식 학습 저장: "+dumps(template))

    def refit_arc(self):
        row=self.selected_row();text,ok=QInputDialog.getText(self,"외곽 호 선택","영상 중심 기준 시계방향 각도 시작,끝 (예: 20,160):")
        if not ok:return
        arc=[float(x.strip()) for x in text.split(",")]
        if len(arc)!=2:raise ValueError("각도 두 값 필요")
        from ..measurement.vision import edge_points,circle_fit
        points,_=edge_points(self.original_image,row["raw_center_px"],row["radius_px"],rays=240,allowed_arc=arc)
        fit=circle_fit(points);reason=self.reason()
        if reason:self.edit("center",{"point_px":fit["center"].tolist(),"radius_px":float(fit["radius"]),
            "sigma_px":float(np.sqrt(np.trace(fit["covariance"][:2,:2])/2)),"arc_deg":arc,"fit_residual_px":fit["residual_rms"]},reason)

    def swap_ids(self):
        value=self.json_dialog("ID 구간 교환 또는 unknown → 고정 ID",{"action":"swap_id","ids":[self.chip_choice.currentText(),"chip_2"],"frames":[self.current_frame,self.slider.maximum()]})
        if value is None:return
        reason=self.reason()
        if reason:self.edit(value["action"],value["ids"] if value["action"]=="swap_id" else value["ids"][1],reason,value["frames"],value["ids"][0])

    def correct_angle(self):
        row=self.selected_row();angle,ok=QInputDialog.getDouble(self,"body rim 각도 보정","반시계 양수, rad",row.get("theta_wrapped_rad") or 0,-3.141593,3.141593,6)
        if ok:
            reason=self.reason()
            if reason:self.edit("angle",{"angle_rad":angle,"sigma_rad":.03},reason)

    def history(self,delta):
        self.require();undo_redo(self.project,delta);self.save();self.log.appendPlainText(f"보정 cursor: {self.project['correction_cursor']} · 새 분석에 반영")

    def start_current(self):
        if not self.current_exp:raise ValueError("검토 영상을 선택하세요.")
        self.queue_table.selectRow(self.project["experiments"].index(self.current_exp));self.start_batch(True)

    def event_selected(self,row):
        if 0<=row<len(self.events):self.slider.setValue(self.events[row]["closest_frame"]);self.review_details.setPlainText(json.dumps(self.events[row],ensure_ascii=False,indent=2))

    def review_event(self,approved):
        i=self.event_table.currentRow()
        if i<0:raise ValueError("사건을 선택하세요.")
        event=self.events[i];kind=event["kind"]
        if approved and kind!="isolated_binary":raise ValueError("미계측/다중접촉 사건을 고립 충돌로 승인할 수 없습니다.")
        if not approved:
            kind,ok=QInputDialog.getItem(self,"사건 분류","제외 유형",[kind,"persistent_contact","out_of_plane_suspected","invalid","unmeasurable"],0,False)
            if not ok:return
        reason=self.reason()
        if reason:self.edit("event",{"status":"approved" if approved else "excluded","kind":kind},reason,[event["frame_start"],event["frame_end"]],event_id=event["id"])

    def build_research(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"4 · 피팅 / 예측 비교")
        v.addWidget(QLabel("단일 칩 μ_b → 정상 e_n → 접선 e_t/μ_c · 학습/보류는 영상 또는 세션 단위 · optimizer 성공과 식별성은 별도"))
        bar=QHBoxLayout();v.addLayout(bar)
        self.button(bar,"현재 run → 피팅 데이터 추가",self.make_fit_data);self.button(bar,"데이터셋 열기",self.open_fit_data);self.button(bar,"단계별 피팅 실행",self.run_fit)
        self.bootstrap_count=QSpinBox();self.bootstrap_count.setRange(0,1000);self.bootstrap_count.setValue(0);bar.addWidget(QLabel("bootstrap 횟수"));bar.addWidget(self.bootstrap_count)
        self.fit_editor=QPlainTextEdit();v.addWidget(self.fit_editor,1)
        buttons=QHBoxLayout();v.addLayout(buttons);self.button(buttons,"피팅 결과 계수 적용",self.apply_fit);self.button(buttons,"현재 run 완전 전방 비교",self.forward)
        self.fit_result=QPlainTextEdit();self.fit_result.setReadOnly(True);v.addWidget(self.fit_result,1);self.last_fit=None

    def make_fit_data(self):
        if not self.current_run:raise ValueError("완료 run을 검토 탭에서 선택하세요.")
        from ..models.research import free_trial,impact_trials
        config=self.json_dialog("피팅 입력 범위",{"kind":"free","chip_id":self.chip_choice.currentText(),"start_frame":self.current_frame,"end_frame":self.slider.maximum()})
        if config is None:return
        dataset=json.loads(self.fit_editor.toPlainText()) if self.fit_editor.toPlainText().strip() else {"split":self.project["fit_split"],"seed":self.project["seed"],"free_trials":[],"impact_trials":[]}
        if config["kind"]=="free":dataset["free_trials"].append(free_trial(self.current_run,config["chip_id"],config["start_frame"],config["end_frame"]))
        else:dataset["impact_trials"].extend(impact_trials(self.current_run))
        self.fit_editor.setPlainText(json.dumps(dataset,ensure_ascii=False,indent=2))

    def open_fit_data(self):
        file,_=QFileDialog.getOpenFileName(self,"피팅 dataset JSON","","JSON (*.json)")
        if file:self.fit_editor.setPlainText(json.dumps(read_json(file),ensure_ascii=False,indent=2))

    def run_fit(self):
        self.require();data=json.loads(self.fit_editor.toPlainText());count=self.bootstrap_count.value()
        from ..models.fitting import fit_dataset
        from ..core.storage import new_id
        out=self.folder/"fits"/new_id("fit");atomic_json(out/"dataset.json",data)
        def done(result):self.last_fit=result;self.fit_result.setPlainText(json.dumps(result,ensure_ascii=False,indent=2))
        self.background(lambda:fit_dataset(data,out,count),done,"피팅·holdout·불확도 계산")

    def apply_fit(self):
        if not self.last_fit:raise ValueError("피팅 결과가 없습니다.")
        for result in self.last_fit["stages"].values():
            if result["physical_status"]!="admissible" or result["diagnostics"]["identifiability"]!="identified_locally":raise ValueError("비물리/비식별 결과는 확정 계수로 적용할 수 없습니다.")
        for result in self.last_fit["stages"].values():self.project["physics"].update(result["parameters"])
        self.project["physics"]["fit_id"]=self.last_fit["id"];self.save();self.load_profile()

    def forward(self):
        if not self.current_run:raise ValueError("완료 run 필요")
        from ..models.research import compare_forward
        self.background(lambda:compare_forward(self.current_run,copy.deepcopy(self.project["physics"])),lambda result:self.fit_result.setPlainText(dumps(result["metrics"])),"완전 전방 예측 비교")

    def build_export(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,"5 · 결과 내보내기")
        v.addWidget(QLabel("CSV·JSONL·JSON·summary.xlsx·그래프·한국어 보고서는 완료 run/export에 저장됩니다. 전체 궤적은 CSV/JSONL로 분리합니다."))
        for label,cb in [("현재 run 출력 갱신",self.export_current),("검토 overlay MP4 생성",self.overlay_current),("전체 완료 run 통합 Excel",self.export_summary),("결과 폴더 열기",self.open_output),("한국어 매뉴얼 열기",self.open_manual)]:self.button(v,label,cb)
        v.addStretch()

    def export_current(self):
        if not self.current_run:raise ValueError("완료 run 필요")
        from ..application.exporting import export_run
        self.background(lambda:export_run(self.current_run),lambda path:self.log.appendPlainText(str(path)),"표·그래프 출력")

    def overlay_current(self):
        if not self.current_run:raise ValueError("완료 run 필요")
        from ..application.exporting import overlay
        run=self.current_run;source=source_path(self.folder,self.current_exp)
        self.background(lambda:overlay(run,source),lambda path:self.log.appendPlainText(str(path)),"원본 재디코딩 overlay")

    def export_summary(self):
        self.require();file,_=QFileDialog.getSaveFileName(self,"통합 요약 저장",str(self.folder/"summary_all.xlsx"),"Excel (*.xlsx)")
        if not file:return
        from ..application.exporting import summary_batch
        runs=[self.folder/e["last_run"] for e in self.project["experiments"] if e.get("last_run") and e.get("status")=="complete"]
        self.background(lambda:summary_batch(runs,file),None,"통합 요약")

    def open_output(self):
        self.require();QDesktopServices.openUrl(QUrl.fromLocalFile(str((self.current_run/"export" if self.current_run else self.folder).resolve())))

    def open_manual(self):
        path=Path(__file__).resolve().parents[3]/"docs/operations/VS_CODE_WINDOWS_KO.md"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self,event):
        if self.batch and self.batch.thread and self.batch.thread.is_alive():
            self.batch.cancel();self.statusBar().showMessage("취소 저장 중입니다. 잠시 후 창을 닫으세요.");event.ignore();return
        if self.busy:event.ignore();self.statusBar().showMessage("현재 작업이 완료된 뒤 닫으세요.");return
        event.accept()


def main(folder=None):
    app=QApplication.instance() or QApplication([]);app.setApplicationName("PokerChip Research")
    window=MainWindow(folder);window.show();return app.exec()
