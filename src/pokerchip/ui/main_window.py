"""v3.0: two inputs, one action, automatic files; advanced science is optional."""
from pathlib import Path
import copy
from PySide6.QtCore import Qt,QUrl,QTimer
from PySide6.QtGui import QColor,QPalette,QDesktopServices
from PySide6.QtWidgets import (QApplication,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,
    QGroupBox,QTableWidgetItem,QFileDialog,QCheckBox,QSpinBox,QComboBox,QAbstractItemView,QScrollArea,
    QProgressBar,QDialog,QFormLayout,QMessageBox)
from .research_window import MainWindow as ExpertWindow,STYLE as BASE_STYLE,label,table
from .forms import number,dialog,buttons
from ..core.config import create_project,register,ensure_chips,save_project
from ..core.storage import read_json
from ..application.automatic import BOARD,run_automatic
from ..application.jobs import Control

STYLE=BASE_STYLE+'''
QWidget {color:#183247;}
QMainWindow,QDialog,QScrollArea {background:#f3f6fa;}
QAbstractItemView {background:#ffffff;color:#183247;alternate-background-color:#f1f5f9;selection-background-color:#d2eaf3;selection-color:#102f41;}
QAbstractItemView::item:selected {background:#d2eaf3;color:#102f41;}
QComboBox QAbstractItemView {background:#ffffff;color:#183247;selection-background-color:#d2eaf3;selection-color:#102f41;border:1px solid #7996a8;outline:0;}
QComboBox QAbstractItemView::item {min-height:28px;}
QListWidget#navigation {background:#153648;color:#e0eef5;}
QListWidget#navigation::item {color:#e0eef5;}
QListWidget#navigation::item:selected {background:#2d6479;color:#ffffff;}
QCheckBox,QRadioButton {color:#20394b;spacing:7px;}
QCheckBox::indicator {width:17px;height:17px;}
QGroupBox::indicator {width:14px;height:14px;border:1px solid #7996a8;background:white;}
QGroupBox::indicator:checked {background:#17667a;}
QMenu,QMenuBar {background:#f8fafc;color:#183247;}
QMenu::item:selected {background:#d2eaf3;color:#102f41;}
QToolTip {background:#163448;color:#ffffff;border:1px solid #9fb1be;padding:6px;}
QLineEdit:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled,QComboBox:disabled {background:#edf1f5;color:#536777;}
QLabel#eyebrow {color:#17667a;font-size:10pt;font-weight:700;}
QLabel#title {font-size:21pt;}
QPushButton#primary {min-height:32px;font-size:12pt;background:#17667a;color:#ffffff;}
QPushButton#primary:disabled {background:#c2d3db;color:#344f60;}
QProgressBar {border:1px solid #cfdae3;background:#e8eef4;color:#163448;text-align:center;min-height:20px;border-radius:5px;}
QProgressBar::chunk {background:#54aabd;border-radius:4px;}
QGroupBox#drop {border:2px dashed #a6becb;background:#ffffff;}
'''


def light_theme(app):
    # Explicit roles fix white-on-white popups under Windows dark/high-contrast themes.
    app.setStyle('Fusion');pal=QPalette()
    roles={'Window':'#f3f6fa','WindowText':'#183247','Base':'#ffffff','AlternateBase':'#f1f5f9',
           'ToolTipBase':'#163448','ToolTipText':'#ffffff','Text':'#183247','Button':'#ffffff',
           'ButtonText':'#183247','BrightText':'#ad2831','Highlight':'#d2eaf3','HighlightedText':'#102f41',
           'Link':'#17667a','PlaceholderText':'#60798a'}
    for group in (QPalette.ColorGroup.Active,QPalette.ColorGroup.Inactive,QPalette.ColorGroup.Disabled):
        for role,color in roles.items():pal.setColor(group,getattr(QPalette.ColorRole,role),QColor(color))
    for role in ('Text','WindowText','ButtonText'):pal.setColor(QPalette.ColorGroup.Disabled,getattr(QPalette.ColorRole,role),QColor('#607383'))
    app.setPalette(pal)


class DropBox(QGroupBox):
    def __init__(self,title,callback):
        super().__init__(title);self.callback=callback;self.setObjectName('drop');self.setAcceptDrops(True)
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
    def dropEvent(self,e):
        paths=[u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:self.callback(paths)
        e.acceptProposedAction()


class MainWindow(ExpertWindow):
    def __init__(self,folder=None):
        light_theme(QApplication.instance());self.quick_control=None;self.quick_running=False;self._last_home_refresh=0.
        super().__init__(None)
        self.setWindowTitle('포커칩 실험 분석 v5.0');self.resize(1380,940);self.setMinimumSize(1050,720)
        self.setStyleSheet(STYLE);self.nav.setObjectName('navigation');self.nav.setFixedWidth(190)
        self.build_quick();self.build_results()
        self.expert_toggle=QCheckBox('세부 설정·물리 피팅 보기')
        self.expert_toggle.toggled.connect(self.set_navigation)
        self.centralWidget().layout().insertWidget(1,self.expert_toggle)
        self.set_navigation(False)
        # Keep diagnostic/project commands, remove the redundant manual save button.
        for b in self.findChildren(QPushButton):
            if b.text()=='저장':b.hide()
            if b.text()=='새 프로젝트':b.setText('새 실험 폴더')
            if b.text()=='프로젝트 열기':b.setText('이전 실험 열기')
            if b.text()=='합성 데모 만들기':b.setText('연습용 예제 만들기')
        self.statusBar().showMessage('보정 영상과 실험 영상을 넣고 분석 시작을 누르세요.')
        self.refresh_home()
        if folder:self.load(folder)

    def set_navigation(self,advanced=False):
        self.nav.blockSignals(True);self.nav.clear()
        self.pages=[6,2,7]+([1,3,0,5,4] if advanced else [])
        self.nav.addItems(['1  영상 넣기','2  이상한 부분 확인','3  저장된 결과']+
            (['세부 촬영·보정 설정','물리계수 계산·비교','영상 작업 관리','검증 상세','추가 내보내기'] if advanced else []))
        self.nav.setCurrentRow(0);self.nav.blockSignals(False);self.tabs.setCurrentIndex(6)

    def build_quick(self):
        scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();scroll.setWidget(page)
        container=QWidget();outer=QVBoxLayout(container);outer.setContentsMargins(0,0,0,0);outer.addWidget(scroll,1)
        self.tabs.addTab(container,'영상 넣기');v=QVBoxLayout(page);v.setSpacing(12)
        v.addWidget(label('POKERCHIP LAB  /  5.0','eyebrow'))
        v.addWidget(label('영상을 넣으면 구간을 찾고, 측정 결과를 저장합니다.','title'))
        v.addWidget(label('검정 칩 · 가장자리 색 표시 한 곳 + 가운데 스티커  |  파일 30 fps → 실제 촬영 240 fps','subtitle'))
        top=QHBoxLayout();v.addLayout(top)
        self.button(top,'보정 영상 선택',self.choose_calibration)
        top.addWidget(label('① 영상 추가  →  ② 자동 분석  →  ③ 확인할 장면만 검토'),1)
        details=QGroupBox('보정 확인란·칩 규격·촬영 설정 펼치기');details.setCheckable(True);details.setChecked(False)
        details.setMaximumHeight(38);details.toggled.connect(lambda on:details.setMaximumHeight(16777215 if on else 38))
        dv=QVBoxLayout(details);detail_content=QWidget();dv.addWidget(detail_content);detail_content.hide()
        details.toggled.connect(detail_content.setVisible);v.addWidget(details)
        grid=QGridLayout(detail_content);grid.setColumnStretch(0,3);grid.setColumnStretch(1,2)
        cal=DropBox('① 보정 영상',lambda paths:self.guarded(lambda:self.set_calibration_path(paths[0])));cv=QVBoxLayout(cal)
        cv.addWidget(label('보정판을 찍은 영상을 여기에 놓으세요.'))
        self.cal_path=label('아직 선택하지 않았습니다.');cv.addWidget(self.cal_path)
        self.button(cv,'보정 영상 선택',self.choose_calibration)
        cv.addWidget(label('첨부한 판 고정: 11 × 8칸 · 한 칸 15 mm · 마커 11 mm'))
        self.floor_check=QCheckBox('보정 영상 끝부분에 판을 실제 바닥에 평평하게 놓았습니다.')
        self.floor_check.setToolTip('끝부분을 재생시간 2초 이상 정지 촬영하세요. 실험 영상의 격자로 평면을 다시 맞추며, 렌즈·줌·초점·해상도는 유지해야 합니다.')
        cv.addWidget(self.floor_check);self.floor_check.toggled.connect(self.quick_settings_changed)
        self.cal_state=label('거리 보정 대기 · 보정 전에도 픽셀 좌표는 저장됩니다.');v.addWidget(self.cal_state)
        grid.addWidget(cal,0,0)
        settings=QGroupBox('이번 실험의 기본값');sv=QVBoxLayout(settings);form=QFormLayout();sv.addLayout(form)
        self.video_mode=QComboBox();self.video_mode.addItem('삼성 240 fps → 30 fps · 1/8배속','samsung')
        self.video_mode.addItem('예전 60 fps · 일반 속도','legacy60');self.video_mode.addItem('불러온 다른 시간 설정 유지','preserve')
        form.addRow('영상 종류',self.video_mode);self.video_mode.currentIndexChanged.connect(self.change_video_mode)
        self.mass=number(.1,1000,3,12);self.mass.setSuffix(' g');form.addRow('칩 한 개의 질량',self.mass)
        self.diameter=number(1,1000,2,40);self.diameter.setSuffix(' mm');form.addRow('칩의 지름',self.diameter)
        self.mass.valueChanged.connect(self.quick_settings_changed);self.diameter.valueChanged.connect(self.quick_settings_changed)
        self.time_hint=label('재생 8초 = 실제 1초\n실제 프레임 간격: 약 0.004167초\n롤링셔터 보정: 사용 안 함');sv.addWidget(self.time_hint)
        self.grid_pitch=number(.1,1000,4,43/18*10);self.grid_pitch.setSuffix(' mm')
        self.grid_pitch.setToolTip('긴 방향 43/18 cm. 영상의 격자 두 방향을 비교해 자동 배정합니다.')
        form.addRow('바닥 격자 긴 변',self.grid_pitch);self.grid_pitch.valueChanged.connect(self.quick_settings_changed)
        self.grid_short=number(.1,1000,4,40.5/18*10);self.grid_short.setSuffix(' mm');form.addRow('바닥 격자 짧은 변',self.grid_short)
        self.grid_short.valueChanged.connect(self.quick_settings_changed)
        sv.addWidget(label('영상별 바닥 격자를 다시 맞춥니다.\n빨강 가장자리+파랑 안쪽 / 파랑 가장자리+노랑 안쪽 표식을 구분합니다.'))
        self.rotation_check=QCheckBox('가장자리 색 표시로 회전도 계산');self.rotation_check.setChecked(True)
        self.rotation_check.setToolTip('기본 최대 회전 가정 500 rad/s (약 80회/초). 회전이 매우 빠르거나 표시가 흐리면 결과를 확인해야 합니다. 세부 설정에서 변경할 수 있습니다.')
        self.rotation_check.toggled.connect(self.quick_settings_changed);sv.addWidget(self.rotation_check)
        sv.addWidget(label('질량·지름은 바꿀 수 있습니다.\n관성모멘트는 균질 원판 I=½mR² 근사입니다.'))
        grid.addWidget(settings,0,1)
        videos=DropBox('② 실험 영상 · 여러 개 한꺼번에 가능',lambda paths:self.guarded(lambda:self.add_paths(paths)))
        vv=QVBoxLayout(videos);bar=QHBoxLayout();vv.addLayout(bar)
        self.button(bar,'실험 영상 추가',self.add_videos)
        self.button(bar,'폴더 영상 추가',self.add_video_folder)
        self.button(bar,'구간 직접 지정 (선택)',self.choose_start)
        self.button(bar,'칩 수 수정',self.edit_experiments)
        self.button(bar,'칩 개수 확인 사진',self.show_count_preview)
        self.button(bar,'선택 영상 빼기',self.remove_video)
        self.intake_table=table(['실험 영상','칩 수','분석 구간 · 자동/직접','상태']);self.intake_table.setMinimumHeight(200);vv.addWidget(self.intake_table)
        self.intake_table.cellDoubleClicked.connect(lambda r,c:self.guarded(lambda:self.choose_start(r)))
        vv.addWidget(label('개수는 자동 제안합니다. 틀리면 직접 바꾸세요. 색 표식이 서로 다른 칩은 가려진 구간 전후를 합쳐 셉니다. 자동 제안은 확인하세요 (설정 최대 32개).'))
        v.addWidget(videos)
        bottom=QHBoxLayout();outer.addLayout(bottom)
        self.output_label=label('저장 위치를 먼저 선택하거나, 영상 추가 시 선택하세요.');bottom.addWidget(self.output_label,1)
        self.button(bottom,'저장 위치 선택',self.new_project)
        self.start_button=self.button(outer,'자동 분석 시작 · 구간 찾기부터 파일 저장까지',self.start_batch);self.start_button.setObjectName('primary')
        self.progress=QProgressBar();self.progress.setRange(0,1);self.progress.setValue(0);self.progress.setFormat('준비');outer.addWidget(self.progress)
        self.video_progress=QProgressBar();self.video_progress.setRange(0,100);self.video_progress.setValue(0);self.video_progress.setFormat('현재 영상 %p%');outer.addWidget(self.video_progress)
        self.progress_text=label('자동 구간 찾기 → 거리 보정 → 위치·회전 측정 → 파일 저장');outer.addWidget(self.progress_text)
        row=QHBoxLayout();outer.addLayout(row)
        self.stop_button=self.button(row,'분석 중단',self.stop_quick);self.stop_button.setEnabled(False)
        self.button(row,'저장된 결과 보기',lambda:self.tabs.setCurrentIndex(7))
        self.button(row,'결과 폴더 열기',self.open_results)

    def build_results(self):
        page=QWidget();v=QVBoxLayout(page);self.tabs.addTab(page,'저장된 결과')
        v.addWidget(label('파일 저장과 측정 상태를 한눈에 확인하세요.','title'))
        self.result_note=label('아직 분석한 영상이 없습니다.');v.addWidget(self.result_note)
        self.result_table=table(['영상','칩 수','처리 상태','위치·속도','회전','확인할 프레임']);v.addWidget(self.result_table,1)
        self.result_table.cellDoubleClicked.connect(lambda r,c:self.guarded(lambda:self.select_experiment(r)))
        v.addWidget(label('초록: 계산·저장 완료  /  노랑: 가정에 따른 잠정값 또는 확인 필요  /  빨강: 처리 실패\n초록 표시도 실제 실험의 정확도를 보증하지는 않습니다.'))
        row=QHBoxLayout();v.addLayout(row);self.button(row,'결과 폴더 열기',self.open_results).setObjectName('primary')
        self.button(row,'선택 영상의 이상한 부분 확인',self.review_selected)
        self.button(row,'선택 영상의 물리 분석 요약',self.physics_summary)
        self.button(row,'추적 표시 영상 저장',self.export_review_video)
        self.button(row,'자동 측정이 맞는지 직접 비교하는 방법',self.explain_accuracy)
        group=QGroupBox('계수 측정 → 계수 고정 → 다른 영상에서 검증');v.addWidget(group);study=QVBoxLayout(group)
        study.addWidget(label('몇 개 영상에서 공통 계수를 피팅하고, 나머지 영상은 그 계수를 바꾸지 않고 비교합니다.'))
        row=QHBoxLayout();study.addLayout(row)
        self.button(row,'① 영상 용도 나누기',self.study_roles)
        self.button(row,'② 측정용 영상으로 계수 구하기',self.study_train)
        self.button(row,'③ 저장 계수로 검증 영상 비교',self.study_test)
        self.study_hint=label('용도를 먼저 지정하세요. 검증 영상은 피팅에 사용하지 않습니다.');study.addWidget(self.study_hint)

    def build_review(self):
        super().build_review()
        page=self.tabs.widget(2);v=page.layout()
        group=QGroupBox('자동 측정의 오차를 직접 비교하기 (선택)');group.setCheckable(True);group.setChecked(False)
        gv=QVBoxLayout(group);content=QWidget();bar=QHBoxLayout(content);gv.addWidget(content);content.hide()
        group.toggled.connect(content.setVisible)
        targets=['자동 측정이 맞는지 직접 확인…','내가 표시한 위치와 비교','비교용 표시 수정 잠금']
        for b in page.findChildren(QPushButton):
            if b.text() in targets:
                b.setParent(content);bar.addWidget(b)
        v.addWidget(group)
        from PySide6.QtWidgets import QSizePolicy
        for g in page.findChildren(QGroupBox):
            if not g.isCheckable():continue
            if g.title()=='표식 학습·ID·각도 도구':g.setTitle('표시 색·칩 번호·각도 직접 수정 (선택)')
            g.setStyleSheet('QGroupBox {padding:0;margin-top:8px;border:0;background:transparent;}')
            g.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Maximum)
            g.setMaximumHeight(32 if not g.isChecked() else 16777215)
            g.toggled.connect(lambda checked,g=g:g.setMaximumHeight(16777215 if checked else 32))
        self.canvas.setMinimumHeight(200);self.event_table.setMaximumHeight(125)
        self.review_timer=QTimer(self);self.review_timer.setInterval(100)
        self.review_timer.timeout.connect(self.review_advance)
        layout=self.slider.parentWidget().layout();controls=QHBoxLayout();layout.insertLayout(layout.indexOf(self.slider)+1,controls)
        for text,delta in [('◀ 10',-10),('◀ 1',-1),('1 ▶',1),('10 ▶',10)]:
            self.button(controls,text,lambda d=delta:self.slider.setValue(self.slider.value()+d))
        self.review_play=self.button(controls,'재생',self.toggle_review_play)
        self.frame_spin=QSpinBox();self.frame_spin.setRange(0,10000000);self.frame_spin.setPrefix('프레임 ');controls.addWidget(self.frame_spin)
        self.frame_spin.setKeyboardTracking(False)
        self.frame_spin.valueChanged.connect(self.slider.setValue)
        self.slider.valueChanged.connect(lambda f:(self.frame_spin.blockSignals(True),self.frame_spin.setValue(f),self.frame_spin.blockSignals(False)))
        zoom=QHBoxLayout();layout.addLayout(zoom)
        self.button(zoom,'- 축소',lambda:self.image_view.zoom_at(1/1.3));self.button(zoom,'+ 확대',lambda:self.image_view.zoom_at(1.3))
        self.button(zoom,'전체 보기',self.image_view.reset_view)
        self.zoom_label=label('100%');zoom.addWidget(self.zoom_label);self.image_view.zoomChanged.connect(lambda z:self.zoom_label.setText(f'{z*100:.0f}%'))
        self.click_mode.currentTextChanged.connect(lambda text:setattr(self.image_view,'point_mode',text!='확대·조회'))
        self.image_view.point_mode=self.click_mode.currentText()!='확대·조회'
        layout.addWidget(label('왼쪽: 선택 도구로 점 지정 / 조회 도구로 이동 · 오른쪽 드래그: 이동 · 휠/±: 확대'))
        for b in page.findChildren(QPushButton):
            if b.text()=='사건 승인':b.setText('충돌로 확인')
            if b.text()=='사건 제외 / 종류':b.setText('충돌이 아님 / 구분')
        for title in page.findChildren(QLabel):
            if title.text()=='문제 프레임을 확인하고 근거를 남기세요':title.setText('자동 분석이 놓친 부분만 확인하세요.')

    def toggle_review_play(self):
        if self.review_timer.isActive():self.review_timer.stop();self.review_play.setText('재생')
        else:self.review_timer.start();self.review_play.setText('일시정지')

    def review_advance(self):
        if getattr(self,'displayed_frame',None)!=self.slider.value():return
        if self.slider.value()>=self.slider.maximum():self.review_timer.stop();self.review_play.setText('재생');return
        self.slider.setValue(self.slider.value()+1)

    def load_review_data(self):
        super().load_review_data()
        if self.current_run and hasattr(self,'review_summary'):
            q=read_json(self.current_run/'export/quality.json')
            self.review_summary.setText(f"선택 구간 위치 기록 {(q.get('observed_fraction_selected_intervals',q['observed_fraction_all_target_frames']) or 0):.1%} · 확인할 프레임 {q.get('review_frame_count',0)}개 · 충돌 후보 {q['event_candidates']}개. 위치 기록 비율은 정확도가 아닙니다.")
        elif self.current_exp and hasattr(self,'review_summary'):
            self.review_summary.setText(self.current_exp['name']+' · 분석 전 원본 미리보기입니다. 시작 프레임은 영상 넣기 화면에서 지정하세요.')
        mapping={'review_required':'확인 필요','approved':'충돌 확인됨','excluded':'제외됨','isolated_binary':'두 칩 충돌',
                 'simultaneous_multi_contact':'여러 칩 동시 접촉','near_simultaneous':'연속 접촉 의심','persistent_contact':'접촉 지속','noncontact_pass':'비접촉 통과','invalid':'충돌 조건 불충족','unmeasurable':'계산할 자료 부족'}
        for i in range(self.event_table.rowCount()):
            for j in (1,3):
                item=self.event_table.item(i,j)
                if item:item.setText(mapping.get(item.text(),item.text()))

    def preview_ready(self,value):
        super().preview_ready(value)
        if value[0]!=self.preview_token:return
        self.displayed_frame=value[1]['frame_index']
        self.frame_spin.setMaximum(self.slider.maximum())
        self.frame_label.setText(self.frame_label.text().replace('declared_provisional','촬영 설정에 따른 시간').replace('synthetic_known_clock','합성 예제 시간'))

    def edit(self,*args,**kwargs):
        if self.quick_running:raise ValueError('분석이 끝난 뒤 위치를 수정하세요.')
        if getattr(self,'displayed_frame',None)!=self.current_frame:raise ValueError('프레임이 표시된 뒤 점을 선택하세요.')
        return super().edit(*args,**kwargs)

    def history(self,*args):
        if self.quick_running:raise ValueError('분석이 끝난 뒤 수정 이력을 바꾸세요.')
        return super().history(*args)

    def ensure_workspace(self):
        if self.project is None:self.new_project()
        return self.project is not None

    def new_project(self):
        if self.quick_running or self.busy:raise ValueError('진행 중인 작업이 끝난 후 새 실험 폴더를 여세요.')
        folder=QFileDialog.getExistingDirectory(self,'분석 결과를 저장할 빈 폴더 선택')
        if folder:
            if (Path(folder)/'project.json').exists():self.load(folder)
            else:
                p=create_project(folder);p['quick_setup']['omega_bound_rad_s']=500.
                p['analysis'].update(identity_mode='spatial_tracks',omega_bound_rad_s=500.)
                save_project(folder,p);self.load(folder)

    def choose_calibration(self):
        file,_=QFileDialog.getOpenFileName(self,'보정판을 촬영한 영상 선택','','영상 (*.mp4 *.mov *.mkv *.avi)')
        if file:self.set_calibration_path(file)

    def set_calibration_path(self,file):
        if self.quick_running:raise ValueError('분석 중에는 영상을 바꿀 수 없습니다.')
        if not self.ensure_workspace():return
        self.project.setdefault('quick_setup',{})['calibration_video']=str(Path(file).resolve())
        self.quick_settings_changed();self.refresh_home()

    def quick_settings_changed(self,*args):
        if not hasattr(self,'intake_table') or self.project is None or self.quick_running:return
        p=self.project;setup=p.setdefault('quick_setup',{})
        setup.update(floor_confirmed=self.floor_check.isChecked(),rolling_shutter_correction=False,
            floor_grid_spacing_m=self.grid_pitch.value()/1000,
            floor_grid_pitches_m=sorted([self.grid_short.value()/1000,self.grid_pitch.value()/1000]),
            omega_bound_rad_s=(p['analysis'].get('omega_bound_rad_s') or 500.) if self.rotation_check.isChecked() else None)
        for c in p['chips']:
            c.update(mass_kg=self.mass.value()/1000,radius_m=self.diameter.value()/2000)
        # Preserve original time and geometry when opening legacy projects.
        save_project(self.folder,p)

    def change_video_mode(self,*args):
        if self.project is None or self.quick_running:return
        mode=self.video_mode.currentData()
        if mode=='preserve':return
        fps,factor=(240.,8.) if mode=='samsung' else (60.,1.)
        t=self.project['time_profile'];t.update(status='declared',capture_fps=fps,evidence='사용자가 선택한 영상 종류',
            preset='samsung_fhd240_8x' if mode=='samsung' else 'legacy60_normal',
            segments=[{'p_start':0.,'p_end':None,'t_start':0.,'slow_factor':factor}])
        t.pop('clock_validation',None);self.quick_settings_changed();self.refresh_home()

    def add_paths(self,paths):
        if self.quick_running:raise ValueError('분석 중에는 영상을 추가할 수 없습니다.')
        paths=[str(Path(p)) for p in paths if Path(p).suffix.lower() in ('.mp4','.mov','.mkv','.avi','.m4v')]
        if not paths:raise ValueError('MP4, MOV 등 영상 파일을 넣어주세요.')
        if not self.ensure_workspace():return
        from ..core.config import source_path
        existing={str(source_path(self.folder,e).resolve()) for e in self.project['experiments']}
        paths=[p for p in paths if str(Path(p).resolve()) not in existing]
        for e in register(self.folder,self.project,paths,['chip_1']):e.update(count_mode='auto',quick_workflow=True)
        self.save();self.refresh_queue();self.refresh_home()

    def add_video_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'하위 폴더 포함 영상 추가')
        if folder:self.add_paths([str(p) for p in sorted(Path(folder).rglob('*')) if p.is_file()])

    def export_review_video(self):
        self.require()
        if self.busy or self.quick_running:raise ValueError('진행 중인 작업이 끝난 뒤 저장하세요.')
        row=self.result_table.currentRow()
        if row<0:raise ValueError('결과 목록에서 영상을 선택하세요.')
        e=self.project['experiments'][row]
        if e.get('status')!='complete' or not e.get('last_run'):raise ValueError('완료한 분석 결과가 필요합니다.')
        from ..core.config import source_path
        from ..application.exporting import overlay
        run=self.folder/e['last_run'];source=source_path(self.folder,e)
        self.background(lambda:str(overlay(run,source)),lambda path:self.statusBar().showMessage('추적 표시 영상 저장: '+path),'원본과 추적 결과를 겹친 영상 저장 중')

    def selected_experiments(self):
        if hasattr(self,'intake_table') and self.tabs.currentIndex()==6:
            rows=sorted({i.row() for i in self.intake_table.selectedIndexes()})
            if not rows:raise ValueError('목록에서 영상을 먼저 선택하세요.')
            return [self.project['experiments'][i] for i in rows]
        return super().selected_experiments()

    def edit_experiments(self):
        if self.quick_running:raise ValueError('분석이 끝난 후 수정하세요.')
        selected=self.selected_experiments();d,v=dialog(self,'칩 개수 수정')
        v.addWidget(label('0은 자동 인식입니다. 알고 있는 개수를 넣으면 자동 개수 대신 사용합니다.'))
        count=QSpinBox();count.setRange(0,32);count.setSpecialValueText('자동 인식')
        count.setValue(0 if selected[0].get('count_mode')=='auto' else len(selected[0]['participating_chip_ids']))
        v.addWidget(count);buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        for e in selected:
            e['count_mode']='auto' if count.value()==0 else 'manual'
            if count.value():e['participating_chip_ids']=ensure_chips(self.project,count.value())
            e['status']='pending'
        self.save();self.refresh_queue();self.refresh_home()

    def remove_video(self):
        if self.quick_running:raise ValueError('분석이 끝난 후 목록을 바꾸세요.')
        ids={e['id'] for e in self.selected_experiments()}
        self.project['experiments']=[e for e in self.project['experiments'] if e['id'] not in ids]
        self.save();self.refresh_queue();self.refresh_home()

    def show_count_preview(self):
        e=self.selected_experiments()[0];path=self.folder/'intake'/e['id']/'count_preview.jpg'
        if not path.exists():raise ValueError('분석을 시작하면 칩 개수 확인 사진이 만들어집니다.')
        import cv2,numpy as np
        from .review_base import ImageView
        d,v=dialog(self,'자동으로 센 칩 확인');d.resize(900,720)
        v.addWidget(label('표본 프레임에서 찾은 원입니다. 실제 칩 개수와 다르면 닫은 뒤 칩 수를 수정하세요.'))
        view=ImageView();view.set_image(cv2.imdecode(np.fromfile(str(path),dtype=np.uint8),cv2.IMREAD_COLOR));v.addWidget(view,1);buttons(d,v);d.exec()

    def choose_start(self,row=None):
        self.require()
        if self.quick_running or self.busy:raise ValueError('현재 작업이 끝난 뒤 시작 구간을 바꾸세요.')
        selected=[self.project['experiments'][row]] if isinstance(row,int) else self.selected_experiments()
        from .viewer import StartFrameDialog
        from ..measurement.selection import confirm_start
        from ..core.config import source_path
        for e in selected:
            path=source_path(self.folder,e);d=StartFrameDialog(path,e,self)
            if d.exec()!=QDialog.DialogCode.Accepted:break
            end=d.selected_end
            confirm_start(e,path,d.selected_frame,end)
            self.save();self.refresh_queue();self.refresh_home()

    def start_batch(self,selected=False):
        self.require()
        if self.quick_running or self.busy:raise ValueError('이미 분석 중입니다.')
        if not self.project['experiments']:raise ValueError('실험 영상을 먼저 추가하세요.')
        ids=[e['id'] for e in self.selected_experiments()] if selected else None
        self.quick_settings_changed();snapshot=copy.deepcopy(self.project);self.quick_control=Control()
        self.quick_running=True;self.start_button.setEnabled(False);self.stop_button.setEnabled(True)
        self.progress.setRange(0,100);self.progress.setValue(0);self.progress.setFormat('전체 작업 %p%');self.video_progress.setValue(0);self.progress_text.setText('보정 준비 중 · 영상 진행률은 측정 시작 후 표시됩니다.')
        self.nav.setEnabled(False)
        for w in (self.mass,self.diameter,self.floor_check,self.rotation_check,self.grid_pitch,self.grid_short,self.video_mode):w.setEnabled(False)
        self.background(lambda:run_automatic(self.folder,snapshot,self.quick_control,self.signals.job.emit,ids),self.quick_done,'자동 분석 시작',allow_project_updates=True)

    def quick_done(self,result):
        self.project=result['project'];self.quick_running=False;self.busy=False
        self.unlock_quick();self.refresh_queue();self.setup.refresh();self.refresh_home()
        self.progress.setRange(0,1);self.progress.setValue(1)
        failures=sum(r.get('status')=='failed' for r in result['results'])
        self.progress.setFormat('중단됨' if result['cancelled'] else f'처리 종료 · 실패 {failures}개' if failures else '측정·파일 저장 완료')
        self.progress_text.setText(f'처리 {len(result["results"])}개 · 실패 {failures}개. 결과표에서 거리 보정과 확인할 장면을 보세요.')
        self.tabs.setCurrentIndex(7)

    def unlock_quick(self):
        if not hasattr(self,'start_button'):return
        self.start_button.setEnabled(True);self.stop_button.setEnabled(False)
        self.nav.setEnabled(True)
        for w in (self.mass,self.diameter,self.floor_check,self.rotation_check,self.grid_pitch,self.grid_short,self.video_mode):w.setEnabled(True)

    def stop_quick(self):
        if self.quick_control:self.quick_control.cancel();self.progress_text.setText('현재 프레임 처리가 끝나면 중단하고 완료된 파일을 저장합니다.')

    def error(self,text):
        self.quick_running=False;self.unlock_quick()
        if hasattr(self,'progress'):self.progress.setRange(0,1);self.progress.setValue(0)
        super().error(text)

    def job_update(self,value):
        if value.get('stage')=='study':
            self.statusBar().showMessage(value['message']);self.log.appendPlainText(value['message']);return
        if not self.quick_running:return super().job_update(value)
        stage=value.get('stage',value.get('status',''))
        if 'overall_percent' in value:
            self.progress.setValue(round(value['overall_percent']));self.video_progress.setValue(round(value['video_percent']))
        names={'interval':'시작·끝 자동 탐색 중','geometry':'여러 프레임의 격자 일치 확인 중','export':'결과 파일 저장 중','calibrating':'보정판 찾고 거리 변환 확인 중','counting':'칩 개수 자동 확인 중','detect':'칩 중심과 색 표시 추적 중',
               'analysis':'충돌 후보 확인 중','kinematics':'속도·회전 계산 중','complete':'데이터 저장 완료','failed':'처리 실패 · 다음 영상 진행'}
        frame=value.get('frame');prefix=(f"{value['video_index']}/{value['video_total']}번째 영상 · {value.get('video_name','')} · " if value.get('video_index') else '보정 영상 · ')
        self.progress_text.setText(prefix+names.get(stage,'분석 중')+(f' · 프레임 {frame}' if frame is not None else '')+' (단계별 진행률)')
        if value.get('experiment_id'):
            e=next((e for e in self.project['experiments'] if e['id']==value['experiment_id']),None)
            if e:e['status']=value.get('status',stage)
        self.log.appendPlainText(str(value))
        import time
        now=time.monotonic()
        if now-self._last_home_refresh>.75 or stage in ('complete','failed','cancelled'):
            self._last_home_refresh=now;self.refresh_home()

    def refresh_home(self):
        if not hasattr(self,'intake_table'):return super().refresh_home()
        if not self.project:return
        self.output_label.setText('저장 위치: '+str(self.folder/'results'))
        q=self.project.get('quick_setup',{});path=q.get('calibration_video')
        self.cal_path.setText(Path(path).name if path else '보정 영상 없음 · 픽셀 좌표로 먼저 분석할 수 있습니다.')
        self.cal_path.setToolTip(str(path or ''))
        for w in (self.mass,self.diameter,self.floor_check,self.rotation_check,self.grid_pitch,self.grid_short):w.blockSignals(True)
        self.mass.setValue((self.project['chips'][0].get('mass_kg') or .012)*1000)
        self.diameter.setValue((self.project['chips'][0].get('radius_m') or .02)*2000)
        self.floor_check.setChecked(q.get('floor_confirmed',False));self.rotation_check.setChecked(q.get('omega_bound_rad_s',500.) is not None)
        pitches=q.get('floor_grid_pitches_m',[.405/18,.430/18]);self.grid_pitch.setValue(max(pitches)*1000);self.grid_short.setValue(min(pitches)*1000)
        for w in (self.mass,self.diameter,self.floor_check,self.rotation_check,self.grid_pitch,self.grid_short):w.blockSignals(False)
        t=self.project['time_profile'];factor=t['segments'][0]['slow_factor'];fps=t.get('capture_fps')
        self.video_mode.blockSignals(True)
        self.video_mode.setCurrentIndex(0 if factor==8 and fps==240 else 1 if factor==1 and fps==60 else 2)
        self.video_mode.blockSignals(False)
        self.time_hint.setText(f'재생시간 ÷ {factor:g} = 실제 시간\n촬영 {fps or "미지정"} fps · 롤링셔터 보정 안 함')
        c=self.project['calibration'];s=c.get('status');err=c.get('holdout_rmse_m')
        self.cal_state.setText(('거리 계산 가능 · '+f'판 내부 확인 오차 {err*1000:.3f} mm (실제 길이 검증 전)' if s=='provisional' and err is not None else
            '거리 보정 확인 완료' if s in ('verified','synthetic') else '거리 보정 필요 · 실제 거리 대신 픽셀 좌표 저장'))
        if c.get('error_message'):self.cal_state.setText('보정 실패: '+c['error_message'])
        elif s=='provisional':self.cal_state.setText(self.cal_state.text()+'\n렌즈 왜곡: '+('보정 적용' if c.get('K') else '자료 부족으로 미보정'))
        elif c.get('automatic_report',{}).get('action'):self.cal_state.setText(self.cal_state.text()+'\n마지막 바닥 정지 구간과 확인란을 확인하세요.')
        metric_count=sum(e.get('calibration',{}).get('H') is not None for e in self.project['experiments'])
        lens='렌즈 보정 있음' if c.get('K') is not None else '렌즈 보정 없음'
        plane='기본 바닥 평면 있음' if c.get('H') is not None else '기본 바닥 평면 미확정'
        cal_detail=self.cal_state.text()
        self.cal_state.setText(f'{lens} · {plane}\n영상별 거리 보정 {metric_count}/{len(self.project["experiments"])}개 · 적용 상태는 결과표에서 확인'+('\n'+cal_detail if c.get('error_message') or c.get('automatic_report',{}).get('action') else ''))
        if c.get('K') is None and not path:
            self.cal_state.setText(self.cal_state.text()+'\n격자 보정이 실패하면 먼저 「보정 영상 선택」으로 렌즈 왜곡을 보정하세요.')
        self.cal_state.setStyleSheet('color:#80530c;')
        exps=self.project['experiments'];self.intake_table.setRowCount(len(exps));self.result_table.setRowCount(len(exps))
        if hasattr(self,'study_hint'):
            train=sum(e.get('fit_role')=='train' for e in exps);test=sum(e.get('fit_role')=='test' for e in exps)
            bank=self.project.get('constant_bank')
            self.study_hint.setText(f'계수 측정용 {train}개 · 고정 계수 검증용 {test}개 · '+('저장한 계수 있음' if bank else '계수 파일 없음'))
        complete=failed=review=0
        for i,e in enumerate(exps):
            count=len(e['participating_chip_ids']);proposal=e.get('count_proposal',{})
            cs=f'{count}개 (직접 지정)' if e.get('count_mode')!='auto' else f"{proposal['count']}개 (자동 · {'확인 필요' if proposal.get('status')=='review_required' else '반복 관측'})" if proposal else '자동 인식 예정'
            state={'counting':'칩 수 확인 중','pending':'분석 대기','failed':'실패 · 확인 필요','cancelled':'중단됨','complete':'저장 완료'}.get(e.get('status'),self.status_text(e.get('status','pending')))
            start=e.get('start_selection',{});start_text=(f"{start['frame']} → {start.get('end') if start.get('end') is not None else '끝'} · 확인됨" if start.get('confirmed') else '자동 탐색' if not start else '자동 구간 · 해제 확인 전')
            for j,value in enumerate([e['name'],cs,start_text,state]):self.intake_table.setItem(i,j,QTableWidgetItem(value))
            result={}
            if e.get('last_run') and e.get('status')=='complete':
                file=self.folder/e['last_run']/'export/quality.json'
                if file.exists():result=read_json(file)
            stale=False
            if result and not self.quick_running:
                from ..application.pipeline import stage_keys
                from ..core.config import effective
                m=read_json(self.folder/e['last_run']/'manifest.json')
                stale=stage_keys(effective(self.project,e),e,m['source_hash'])['export']!=m.get('stage_keys',{}).get('export')
                if stale:state='설정 변경 · 다시 분석 필요'
            if result and not stale and result.get('measurement_status')=='review_required':state='저장됨 · 측정 확인 필요'
            complete+=e.get('status')=='complete';failed+=e.get('status')=='failed';review+=result.get('review_frame_count',0)
            geo=result.get('geometry_status');motion='계산됨' if geo in ('verified','synthetic') else '잠정 계산' if geo=='provisional' else '픽셀 좌표만'
            values=[e['name'],cs,state,motion if result else '—',(f"{result.get('angular_velocity_rows',0)}행 · 잠정" if result.get('angular_velocity_rows') else '회전 누락 · 확인 필요') if result else '—',str(result.get('review_frame_count','—'))]
            for j,value in enumerate(values):
                item=QTableWidgetItem(value)
                if j==1 and proposal:item.setForeground(QColor('#8a580d'));item.setToolTip('가려진 칩은 적게 셀 수 있습니다. 영상 넣기의 칩 개수 확인 사진을 보거나 직접 수정하세요.')
                if j==2:item.setForeground(QColor('#ad2831' if e.get('status')=='failed' else '#806016' if stale or result.get('measurement_status')=='review_required' else '#146748' if e.get('status')=='complete' else '#806016'))
                if j==3 and geo=='provisional':item.setForeground(QColor('#8a580d'))
                if j==4 and result and not result.get('angular_velocity_rows'):item.setForeground(QColor('#ad2831'))
                item.setToolTip(e.get('failure_reason',''))
                self.result_table.setItem(i,j,item)
        self.result_note.setText(f'영상 {len(exps)}개 · 저장 완료 {complete}개 · 실패 {failed}개 · 확인할 프레임 {review}개\n전체_운동데이터.csv와 영상별_요약.xlsx가 results 폴더에 자동으로 저장됩니다.')

    def load(self,folder):
        if self.quick_running:raise ValueError('분석을 중단한 뒤 폴더를 바꾸세요.')
        super().load(folder)
        if hasattr(self,'intake_table'):self.tabs.setCurrentIndex(6)

    def review_selected(self):
        row=self.result_table.currentRow()
        if row<0:raise ValueError('결과 목록에서 영상을 선택하세요.')
        self.select_experiment(row)
        if self.current_run:self.jump_issue(1)

    def open_results(self):
        self.require();out=self.folder/'results'
        if not out.exists():raise ValueError('분석이 끝나면 결과 폴더가 생성됩니다.')
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))

    def explain_accuracy(self):
        QMessageBox.information(self,'자동 측정이 맞는지 확인하기','이상한 부분 확인 화면에서 원본을 보고 칩 중심을 직접 표시할 수 있습니다.\n자동으로 찾은 중심과 내가 표시한 중심의 차이를 비교합니다.\n이 검사는 선택 사항이며, 일반 분석과 파일 저장에는 필요하지 않습니다.')

    def physics_summary(self):
        self.require();i=self.result_table.currentRow()
        if i<0:raise ValueError('결과에서 영상을 먼저 선택하세요.')
        e=self.project['experiments'][i]
        if not e.get('last_run'):raise ValueError('먼저 분석을 실행하세요.')
        path=self.folder/e['last_run']/'export/physics_preview.json'
        if not path.exists():raise ValueError('v5.0는 영상 측정과 물리 피팅을 분리합니다. 아래 ① 영상 용도 나누기 → ② 계수 구하기를 사용하세요.')
        data=read_json(path);lines=['탐색 계산입니다. 검증된 최종 계수나 정확도가 아닙니다.']
        for f in data.get('free_motion',[]):
            if f.get('mu_bottom') is not None:lines.append(f"{f['chip_id']}: 바닥 마찰 추정 {f['mu_bottom']:.4f}, 위치 적합 오차 {f['position_fit_rmse_m']*1000:.2f} mm ({f['status']})")
            else:lines.append(f"{f['chip_id']}: 연속된 이동·회전 자료 부족 또는 피팅 실패")
        for ev in data.get('impacts',[]):
            en=ev.get('e_n_obs') if ev.get('kind')=='isolated_binary' else None;lines.append(f"충돌 후보 {ev['id']}: 법선 반발 관측값 {en:.3f}" if en is not None else f"충돌 후보 {ev['id']}: 전후 자료 확인 필요")
        lines.append('접선 반발과 접촉 마찰은 여러 검토된 충돌로 따로 피팅해야 합니다.')
        QMessageBox.information(self,'물리 분석 · 잠정 결과','\n\n'.join(lines))

    def study_roles(self):
        self.require()
        if self.quick_running or self.busy:raise ValueError('진행 중인 작업이 끝난 뒤 용도를 바꾸세요.')
        d,v=dialog(self,'계수 측정용 / 고정 계수 검증용 영상');d.resize(930,530)
        v.addWidget(label('계수를 구할 영상과 남겨둘 검증 영상을 나누세요. 기본값은 제외입니다. 같은 촬영일의 검증은 공통 보정 오차를 공유합니다.'))
        t=table(['영상','용도','충돌 장면 확인']);v.addWidget(t);t.setRowCount(len(self.project['experiments']));controls=[]
        for i,e in enumerate(self.project['experiments']):
            t.setItem(i,0,QTableWidgetItem(e['name']));combo=QComboBox()
            for title,key in [('이번 계수 연구에서 제외','exclude'),('계수 구하기용','train'),('고정 계수 검증용','test')]:combo.addItem(title,key)
            combo.setCurrentIndex(max(0,combo.findData(e.get('fit_role','exclude'))));t.setCellWidget(i,1,combo)
            check=QCheckBox('충돌 승인은 영상 검토 화면에서 건별로');check.setChecked(False);check.setEnabled(False);t.setCellWidget(i,2,check);controls.append((e,combo,check))
        v.addWidget(label('충돌 확인란은 원본과 검출 결과를 직접 확인한 뒤 체크하세요. 자유운동 피팅에는 필요하지 않습니다. 접선 반발·충돌 마찰 분리에는 서로 다른 충돌 조건이 필요합니다.'))
        buttons(d,v)
        if d.exec()!=QDialog.DialogCode.Accepted:return
        for e,combo,check in controls:e.update(fit_role=combo.currentData(),impacts_reviewed=check.isChecked())
        self.save();self.refresh_home()

    def study_train(self):
        self.require()
        if self.quick_running or self.busy:raise ValueError('진행 중인 작업이 끝난 뒤 실행하세요.')
        from ..models.study import train_constants,preflight
        checks=preflight(self.folder,self.project)
        if not any(r['usable'] for r in checks):raise ValueError('피팅 가능한 영상이 없습니다.\n'+'\n'.join(r['reason'] for r in checks))
        if QMessageBox.question(self,'피팅 대상 확인','\n'.join(r['video']+' · '+r['reason'] for r in checks)+'\n\n사용 가능한 영상으로 진행합니다.')!=QMessageBox.StandardButton.Yes:return
        folder=self.folder;snapshot=copy.deepcopy(self.project)
        self.background(lambda:train_constants(folder,snapshot,progress=self.signals.job.emit),self.study_trained,'측정용 영상의 공통 계수 피팅')

    def study_trained(self,result):
        self.project['constant_bank']=str(Path(result['path']).relative_to(self.folder));self.save();self.refresh_home()
        QMessageBox.information(self,'계수 저장 완료','저장한 계수: '+str(result['parameters'])+'\n\n잠정 피팅 결과입니다. 이제 ③ 저장 계수로 검증 영상 비교를 실행하세요.\n'+result['path'])

    def study_test(self):
        self.require()
        if self.quick_running or self.busy:raise ValueError('진행 중인 작업이 끝난 뒤 실행하세요.')
        if not self.project.get('constant_bank'):raise ValueError('② 계수 구하기를 먼저 실행하세요.')
        from ..models.study import evaluate_fixed
        folder=self.folder;snapshot=copy.deepcopy(self.project);bank=folder/self.project['constant_bank']
        self.background(lambda:evaluate_fixed(folder,snapshot,bank,progress=self.signals.job.emit),self.study_tested,'계수를 고정한 다른 영상 예측')

    def study_tested(self,result):
        QMessageBox.information(self,'고정 계수 검증 저장','계수를 다시 피팅하지 않고 비교했습니다.\n상태: '+('비교 완료' if result['status']=='conditional_holdout_evaluated' else '검증할 유효 구간 부족')+'\n'+result['path'])

    def open_manual(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[3]/'docs/operations/README_V5_KO.md')))

    def closeEvent(self,event):
        if self.quick_running:
            self.stop_quick();event.ignore();self.statusBar().showMessage('중단 후 저장 중입니다. 잠시 뒤 다시 닫아주세요.');return
        if hasattr(self,'frame_loader'):self.frame_loader.stop()
        if hasattr(self,'review_timer'):self.review_timer.stop()
        super().closeEvent(event)


from .workbench_v45 import ReviewWorkflow

class MainWindow(ReviewWorkflow, MainWindow):
    """v5.0 workflow with the stable v4 compatibility surface."""
    pass

def main(folder=None):
    app=QApplication.instance() or QApplication([]);app.setApplicationName('PokerChip Research v5.0')
    w=MainWindow(folder);w.show();return app.exec()
