"""Exact-frame navigation and bounded cache. No middle mouse dependency."""
from collections import OrderedDict
from pathlib import Path
import threading
import numpy as np
from PySide6.QtCore import Qt, Signal, QObject, QRectF, QTimer
from PySide6.QtGui import QImage, QPainter, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QCheckBox, QApplication, QLineEdit, QAbstractSpinBox
from ..measurement.video import frames, metadata


from ..measurement.frame_access import IndexedFrameReader, Superseded

class ExactFrameReader(IndexedFrameReader):
    pass


class FrameLoader(QObject):
    ready=Signal(object)
    failed=Signal(object)
    def __init__(self, parent=None):
        super().__init__(parent);self.condition=threading.Condition();self.request=None;self.stopped=False;self.generation=0
        self.worker=threading.Thread(target=self._work,daemon=True);self.worker.start()
    def submit(self, token, path, index):
        with self.condition:self.generation+=1;self.request=(token,path,index,self.generation);self.condition.notify()
    def stop(self):
        with self.condition:self.stopped=True;self.condition.notify()
    def _work(self):
        reader=ExactFrameReader()
        try:
            while True:
                with self.condition:
                    while self.request is None and not self.stopped:self.condition.wait()
                    if self.stopped:return
                    token,path,index,generation=self.request;self.request=None
                try:
                    timing,image=reader.get(path,index,cancelled=lambda:self.stopped or generation!=self.generation)
                    if reader.index is not None:timing={**timing,"decoded_count":reader.index["decoded_count"]}
                    if not self.stopped and generation==self.generation:self.ready.emit((token,timing,image))
                except Superseded:
                    continue
                except Exception as exc:
                    if not self.stopped and generation==self.generation:self.failed.emit((token,str(exc)))
        finally:reader.close()


class ImageView(QWidget):
    clicked=Signal(float,float)
    zoomChanged=Signal(float)
    def __init__(self):
        super().__init__();self.image=None;self.target=QRectF();self.setMinimumSize(360,260)
        self.zoom=1.;self.pan=np.zeros(2);self.drag_origin=None;self.point_mode=True;self.cross=None
        self.setMouseTracking(True)
        self.setToolTip('오른쪽 버튼 드래그: 이동 · 휠 또는 ±: 확대 · 점 도구에서 왼쪽 클릭: 위치 지정 · 오른쪽 더블클릭: 전체 보기')
    def set_image(self,bgr):
        rgb=np.ascontiguousarray(bgr[:,:,::-1]);h,w=rgb.shape[:2]
        if self.image is not None and (w,h)!=(self.image.width(),self.image.height()):self.reset_view()
        self.image=QImage(rgb.data,w,h,rgb.strides[0],QImage.Format.Format_RGB888).copy();self.update_rect();self.update()
    def update_rect(self):
        if self.image is None:return
        scale=min(self.width()/self.image.width(),self.height()/self.image.height())*self.zoom
        w,h=self.image.width()*scale,self.image.height()*scale
        self.target=QRectF((self.width()-w)/2+self.pan[0],(self.height()-h)/2+self.pan[1],w,h)
    def resizeEvent(self,event):self.update_rect();super().resizeEvent(event)
    def reset_view(self):
        self.zoom=1.;self.pan[:]=0;self.update_rect();self.update();self.zoomChanged.emit(self.zoom)
    def zoom_at(self,factor,point=None):
        old=self.zoom;new=float(np.clip(old*factor,1,20))
        if point is None:point=np.array([self.width()/2,self.height()/2])
        else:point=np.array([point.x(),point.y()])
        center=np.array([self.width()/2,self.height()/2])
        self.pan=point-center-(point-center-self.pan)*(new/old);self.zoom=new
        if new==1:self.pan[:]=0
        self.update_rect();self.update();self.zoomChanged.emit(new)
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#172d3c'))
        if self.image is None:
            p.setPen(Qt.GlobalColor.white);p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'프레임을 불러오는 중…');return
        self.update_rect();p.drawImage(self.target,self.image)
        if self.cross is not None:
            x=self.target.x()+self.cross[0]*self.target.width()/self.image.width()
            y=self.target.y()+self.cross[1]*self.target.height()/self.image.height()
            p.setPen(QColor('#ffdf60'));p.drawLine(int(x)-9,int(y),int(x)+9,int(y));p.drawLine(int(x),int(y)-9,int(x),int(y)+9)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton or (event.button()==Qt.MouseButton.LeftButton and not self.point_mode):
            self.drag_origin=np.array([event.position().x(),event.position().y()]);return
        if event.button()==Qt.MouseButton.LeftButton and self.image is not None and self.target.contains(event.position()):
            x=(event.position().x()-self.target.x())*self.image.width()/self.target.width()
            y=(event.position().y()-self.target.y())*self.image.height()/self.target.height()
            self.cross=(x,y);self.update();self.clicked.emit(x,y)
    def mouseMoveEvent(self,event):
        if self.drag_origin is not None:
            point=np.array([event.position().x(),event.position().y()]);self.pan+=point-self.drag_origin;self.drag_origin=point
            self.update_rect();self.update()
    def mouseReleaseEvent(self,event):self.drag_origin=None
    def wheelEvent(self,event):self.zoom_at(1.2 if event.angleDelta().y()>0 else 1/1.2,event.position());event.accept()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:self.reset_view()
        elif not self.point_mode:self.zoom_at(1.8,event.position())
    def contextMenuEvent(self,event):event.accept()


class StartFrameDialog(QDialog):
    """Nothing is confirmed until a displayed frame is explicitly accepted."""
    def __init__(self,path,experiment,parent=None):
        super().__init__(parent);self.path=path;self.setWindowTitle('분석 시작 프레임 선택 · '+experiment['name']);self.resize(1050,850)
        self.token=0;self.loaded=-1;self.frame=0;self.selected_frame=None;self.selected_end=None;self.pinned_start=None
        self.total=metadata(path).get('estimated_frames') or 1
        v=QVBoxLayout(self);intro=QLabel('시작과 끝은 어떤 순서로 지정해도 됩니다.\n시작 장면 확인 → 시작 고정 → 끝 장면 지정 → 구간 적용');v.addWidget(intro)
        self.view=ImageView();self.view.point_mode=False;v.addWidget(self.view,1)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(0,self.total-1);v.addWidget(self.slider)
        bar=QHBoxLayout();v.addLayout(bar)
        for title,delta in [('◀ 10',-10),('◀ 1',-1),('1 ▶',1),('10 ▶',10)]:
            b=QPushButton(title);b.clicked.connect(lambda checked=False,d=delta:self.slider.setValue(self.slider.value()+d));bar.addWidget(b)
        self.play=QPushButton('재생');self.play.clicked.connect(self.toggle_play);bar.addWidget(self.play)
        self.spin=QSpinBox();self.spin.setRange(0,self.total-1);self.spin.setPrefix('프레임 ');bar.addWidget(self.spin)
        self.spin.setKeyboardTracking(False)
        for title,fn in [('- 축소',lambda:self.view.zoom_at(1/1.3)),('+ 확대',lambda:self.view.zoom_at(1.3)),('전체 보기',self.view.reset_view),('전체화면 (F11)',self.toggle_fullscreen)]:
            b=QPushButton(title);b.clicked.connect(fn);bar.addWidget(b)
        self.label=QLabel('');v.addWidget(self.label)
        v.addWidget(QLabel('프레임 번호는 0부터 시작 · ←/→ 한 프레임 · Shift+←/→ 열 프레임 · 오른쪽 드래그로 이동'))
        self.end_check=QCheckBox('종료 프레임 제한 (손 재접촉·화면 이탈 이후 제외)');v.addWidget(self.end_check)
        endrow=QHBoxLayout();v.addLayout(endrow);self.end_spin=QSpinBox();self.end_spin.setRange(0,self.total-1);self.end_spin.setPrefix('끝 프레임 ');endrow.addWidget(self.end_spin)
        old_end=experiment.get('interval',[0,None])[1];self.end_spin.setValue(old_end if old_end is not None else self.total-1);self.end_check.setChecked(old_end is not None)
        use_end=QPushButton('현재 장면을 종료로 지정');endrow.addWidget(use_end)
        use_end.clicked.connect(self.pin_end)
        self.pin_start_button=QPushButton('현재 장면을 시작으로 고정');endrow.addWidget(self.pin_start_button)
        self.pin_start_button.clicked.connect(self.pin_start)
        self.range_label=QLabel('시작: 아직 고정하지 않음');v.addWidget(self.range_label)
        self.end_check.toggled.connect(self.update_accept);self.end_spin.valueChanged.connect(self.update_accept)
        self.check=QCheckBox('선택 장면에서 손·고무줄과의 접촉이 끝났음을 확인했습니다.');v.addWidget(self.check)
        actions=QHBoxLayout();v.addLayout(actions);cancel=QPushButton('나중에 선택');cancel.clicked.connect(self.reject);actions.addWidget(cancel)
        self.accept_button=QPushButton('선택한 구간 적용');self.accept_button.setObjectName('primary');self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self.commit);actions.addWidget(self.accept_button)
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.advance)
        self.loader=FrameLoader(self);self.loader.ready.connect(self.ready);self.loader.failed.connect(self.failure)
        self.slider.valueChanged.connect(self.request_frame);self.spin.valueChanged.connect(self.slider.setValue)
        self.check.toggled.connect(self.update_accept)
        self.shortcuts=[]
        full=QShortcut(QKeySequence("F11"),self);full.activated.connect(self.toggle_fullscreen);self.shortcuts.append(full)
        for key,delta in [('Left',-1),('Right',1),('Shift+Left',-10),('Shift+Right',10)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(lambda d=delta:self.slider.setValue(self.slider.value()+d));self.shortcuts.append(shortcut)
        QApplication.instance().focusChanged.connect(self.refresh_frame_shortcuts)
        self.finished.connect(lambda _:self.loader.stop());self.finished.connect(lambda _:self.timer.stop())
        initial=min(self.total-1,experiment.get('interval',[0])[0]);self.slider.setValue(initial)
        if not self.token:self.request_frame(initial)
    def refresh_frame_shortcuts(self,*args):
        for shortcut in self.shortcuts[1:]:shortcut.setEnabled(not isinstance(QApplication.focusWidget(),(QLineEdit,QAbstractSpinBox)))

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def reject(self):
        if self.isFullScreen():self.showNormal()
        else:super().reject()

    def request_frame(self,f):
        self.frame=f;self.token+=1;self.check.setChecked(False) if self.pinned_start is None else None;self.accept_button.setEnabled(False)
        self.spin.blockSignals(True);self.spin.setValue(f);self.spin.blockSignals(False)
        self.label.setText(f'프레임 {f} / {self.total-1} 불러오는 중… 처음 이동할 때는 정확한 프레임 색인을 준비합니다.')
        self.loader.submit(self.token,self.path,f)
    def ready(self,value):
        token,timing,img=value
        if token!=self.token:return
        if timing.get('decoded_count') and timing['decoded_count']!=self.total:
            self.total=timing['decoded_count']
            for widget in (self.slider,self.spin,self.end_spin):widget.blockSignals(True);widget.setMaximum(self.total-1);widget.blockSignals(False)
        self.loaded=timing['frame_index'];self.view.set_image(img)
        p=timing.get('presentation_time_s');self.label.setText(f'프레임 {self.loaded} / {self.total-1} · 파일 재생시간 {p:.4f}초' if p is not None else f'프레임 {self.loaded}')
        self.update_accept()
    def pin_start(self):
        if self.loaded!=self.frame:return
        self.pinned_start=self.frame;self.check.setChecked(True);self.update_accept()
    def pin_end(self):
        if self.loaded!=self.frame:return
        self.end_check.setChecked(True);self.end_spin.setValue(self.frame);self.update_accept()
    def update_accept(self,*args):
        start=self.pinned_start if self.pinned_start is not None else self.frame
        self.accept_button.setEnabled(self.loaded==self.frame and self.check.isChecked() and
            (not self.end_check.isChecked() or self.end_spin.value()>start))
        if hasattr(self,'range_label'):
            self.range_label.setText(f"시작 {start} {'(고정됨)' if self.pinned_start is not None else '(현재 장면)'} → 끝 {self.end_spin.value() if self.end_check.isChecked() else '영상 끝'}")
    def failure(self,value):
        token,message=value
        if token!=self.token:return
        self.timer.stop();self.play.setText('재생');self.label.setText(message)
    def toggle_play(self):
        if self.timer.isActive():self.timer.stop();self.play.setText('재생')
        else:self.timer.start();self.play.setText('일시정지')
    def advance(self):
        if self.loaded!=self.frame:return
        if self.frame==self.total-1:self.timer.stop();self.play.setText('재생');return
        self.slider.setValue(self.frame+1)
    def commit(self):
        if self.accept_button.isEnabled():
            self.selected_frame=self.pinned_start if self.pinned_start is not None else self.frame;self.selected_end=self.end_spin.value() if self.end_check.isChecked() else None;self.accept()
