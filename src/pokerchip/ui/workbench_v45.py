"""Research review workflow; physics remains in the analysis/model services."""
import copy
import numpy as np
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QProgressBar,
    QComboBox,QCheckBox,QSpinBox,QMessageBox,QInputDialog,QSplitter,QTableWidget,QTableWidgetItem,QDialogButtonBox,QMenu,QGroupBox)
from ..core.config import effective
from ..core.review import set_endpoint,validate_boundary
from ..core.storage import Records
from ..application.jobs import Control


class ReviewWorkflow:
    def __init__(self,folder=None):
        self.study_control=None;self.seed_context=None;self._full_dialog=None
        super().__init__(folder)
        self.setWindowTitle('포커칩 연구실 · v5.0')
        self.setMinimumSize(960,680)
        check=Path(__file__).parent/'resources'/'checked.svg'
        self.setStyleSheet(self.styleSheet()+f'''
QCheckBox::indicator {{width:20px;height:20px;border:2px solid #486377;border-radius:3px;background:white;}}
QCheckBox::indicator:checked {{image:url("{check.as_posix()}");background:#17667a;border-color:#12495c;}}
QCheckBox::indicator:disabled {{border-color:#879aa7;background:#dae3e9;}}
QCheckBox::indicator:indeterminate {{background:#4f91a5;}}
QCheckBox:focus {{outline:2px solid #17667a;}}
QGroupBox::indicator {{width:20px;height:20px;border:2px solid #486377;border-radius:3px;background:white;}}
QGroupBox::indicator:checked {{image:url("{check.as_posix()}");background:#17667a;}}
QPushButton {{min-height:24px;padding:4px 8px;}}
QLabel#title {{font-size:16pt;}}
''')
        row=QHBoxLayout();self.work_label=QLabel('작업 대기');row.addWidget(self.work_label,2)
        self.work_progress=QProgressBar();self.work_progress.setRange(0,100);self.work_progress.setValue(0);row.addWidget(self.work_progress,1)
        self.work_cancel=QPushButton('현재 작업 중단');self.work_cancel.clicked.connect(self.cancel_work);row.addWidget(self.work_cancel)
        self.centralWidget().layout().addLayout(row)
        self.button(self.tabs.widget(7).layout(),'계수별 준비 상태 확인',self.show_preflight)
        self.button(self.tabs.widget(7).layout(),'저장한 계수·미산출 이유 보기',self.show_constants)
        page=self.tabs.widget(2);tools=QHBoxLayout();page.layout().insertLayout(4,tools)
        self.button(tools,'영상 전체화면 (F11)',self.full_review)
        actions=QPushButton('이 장면에서 수정할 것');menu=QMenu(actions);actions.setMenu(menu);tools.addWidget(actions)
        for title,fn in [('칩 정지·화면 이탈',self.chip_endpoint),('충돌 직전·직후 장면',self.boundary_dialog),
                         ('놓친 충돌 추가',self.add_missing_event),('클릭한 표식 방향 반영',self.correct_marker)]:
            menu.addAction(title).triggered.connect(lambda checked=False,fn=fn:self.guarded(fn))
        self.show_markers=QCheckBox('표식 표시');self.show_markers.setChecked(True);tools.addWidget(self.show_markers)
        self.show_markers.toggled.connect(lambda _:self.redraw_overlay())
        self.marker_summary=QLabel('원 테두리 = 중심 측정 · 노랑 십자 = 가장자리 · 파랑 십자 = 안쪽 · 표식 없음은 회전 미측정')
        self.marker_summary.setWordWrap(True);self.marker_summary.setMaximumHeight(42)
        page.layout().insertWidget(5,self.marker_summary)
        page.layout().setSpacing(5);self.image_view.setMinimumHeight(240)
        for title in page.findChildren(QLabel):
            if title.objectName()=='subtitle':title.hide()
        for split in page.findChildren(QSplitter):split.setSizes([650,450])
        self.chip_choice.currentTextChanged.connect(self.clear_seeds)
        self.graph_kind.blockSignals(True);self.graph_kind.clear()
        self.graph_kind.addItems(['평면 궤적 (x, y)','칩 쌍 거리 / 측정 품질','시간별 x·y · 회전']);self.graph_kind.blockSignals(False)
        self._fullscreen_key=QShortcut(QKeySequence('F11'),self);self._fullscreen_key.activated.connect(self.full_review)
        for b in page.findChildren(QPushButton):
            if b.text()=='충돌이 아님 / 구분':b.setText('충돌 분류·피팅 제외')
            if b.text()=='표식 학습 저장':b.setText('클릭한 색을 다음 추적에 사용')
        self.task_hint=QLabel('확인할 장면을 선택한 뒤 필요한 작업만 고르세요. 원 테두리·표식·충돌 전후를 각각 확인합니다.')
        self.task_hint.setWordWrap(True);page.layout().insertWidget(0,self.task_hint);self.task_hint.hide()
        advanced_names={'경계 호 재적합','ID 구간 교환','각도 보정','클릭한 색을 다음 추적에 사용','선명한 표식 기준 프레임 제안'}
        self.advanced_review_buttons=[b for b in page.findChildren(QPushButton) if b.text() in advanced_names]
        for b in self.advanced_review_buttons:b.hide()
        self.advanced_review=QCheckBox('고급 수정 도구');tools.addWidget(self.advanced_review)
        self.advanced_review.toggled.connect(lambda on:[b.setVisible(on) for b in self.advanced_review_buttons])
        for widget in page.findChildren(QGroupBox)+page.findChildren(QCheckBox):
            if widget is self.advanced_review or widget is self.show_markers:continue
            if isinstance(widget,QGroupBox) or widget.text()=='상세 수치/수정 로그 보기':
                widget.hide();self.advanced_review.toggled.connect(widget.setVisible)
        self.click_mode.currentTextChanged.connect(self.update_task_hint)
        self.load_review_data()

    def update_task_hint(self,mode):
        help_text={'확대·조회':'오른쪽 드래그로 이동, 휠로 확대합니다. 측정값을 바꾸지 않습니다.',
            '중심 보정 클릭':'선택한 칩의 실제 원 중심을 클릭하세요. 수정 이유를 저장한 후 재분석합니다.',
            '가장자리 색 표시 클릭':'선택 칩의 칠한 가장자리 한 곳을 클릭하세요. 이 장면의 방향 보정이 바로 저장됩니다.',
            '안쪽 스티커 클릭':'스티커 중심을 클릭하세요. 색 학습용입니다. 원판 중심으로 쓰지 않습니다. 고급 도구에서 색 학습을 저장할 수 있습니다.',
            '격자 대응점 클릭':'교차점을 클릭하고 칸 번호를 입력합니다. 거리 보정이 실패한 영상에만 필요합니다.'}
        self.task_hint.setText(help_text.get(mode,''))
        self.task_hint.setVisible(mode!='확대·조회')

    def add_missing_event(self):
        self.require_editable_frame()
        ids=self.current_exp['participating_chip_ids']
        if len(ids)<2:raise ValueError('두 칩 이상인 영상에서 충돌을 추가할 수 있습니다.')
        pairs=[a+' / '+b for i,a in enumerate(ids) for b in ids[i+1:]]
        pair,ok=QInputDialog.getItem(self,'놓친 충돌 추가','현재 장면에서 접촉한 두 칩',pairs,0,False)
        if not ok:return
        f=self.current_frame
        self.edit('add_event',{'pair':pair.split(' / '),'closest_frame':f,'frame_start':max(0,f-2),'frame_end':f+2},
            '원본 영상에서 사람이 발견한 누락 충돌 후보')
        self.review_details.appendPlainText('충돌 후보 저장. 보정 반영 재분석 뒤 전후 장면과 피팅 조건을 확인하세요.')

    def require_editable_frame(self):
        self.require()
        if self.busy or self.quick_running:raise ValueError('계산 중에는 수정할 수 없습니다. 작업이 끝나거나 중단된 뒤 수정하세요.')
        if not self.current_exp or getattr(self,'displayed_frame',None)!=self.current_frame:
            raise ValueError('선택한 프레임이 화면에 표시될 때까지 기다리세요.')
        return (self.current_exp['id'],self.current_frame,self.chip_choice.currentText())

    def clear_seeds(self,*args):
        self.marker_seeds={};self.seed_context=None

    def edit(self,*args,**kwargs):
        self.require_editable_frame()
        return super().edit(*args,**kwargs)

    def refit_arc(self):
        self.require_editable_frame();return super().refit_arc()

    def correct_angle(self):
        self.require_editable_frame();return super().correct_angle()

    def swap_ids(self):
        self.require_editable_frame();return super().swap_ids()

    def correct_marker(self):
        context=self.require_editable_frame()
        if self.seed_context!=context or 'rim' not in self.marker_seeds:raise ValueError('가장자리 색 표시 클릭 도구로 현재 장면의 표식을 먼저 찍으세요.')
        self.edit('marker',{'point_px':self.marker_seeds['rim']},'원본에서 사람이 지정한 가장자리 표식')
        self.review_details.appendPlainText('이 프레임의 각도 보정 저장. 보정 반영 재분석 후 각속도까지 다시 계산합니다.')

    def image_click(self,x,y):
        context=self.require_editable_frame()
        if self.click_mode.currentText()=='격자 대응점 클릭':
            return self.grid_click(x,y)
        if self.seed_context!=context:self.clear_seeds()
        self.seed_context=context
        result=super().image_click(x,y)
        if self.click_mode.currentText()=='가장자리 색 표시 클릭' and 'rim' in self.marker_seeds:
            self.correct_marker()
            self.task_hint.setText('가장자리 방향 보정 저장됨 · 보정 반영 재분석을 누르면 각속도까지 갱신됩니다.')
        return result

    def save_template(self):
        context=self.require_editable_frame()
        if self.seed_context!=context:raise ValueError('현재 영상·프레임·칩에서 표식을 다시 선택하세요.')
        # The base implementation reads project calibration; give it only the effective
        # per-video view, then commit template data, never replace project calibration.
        original=self.project;working=copy.deepcopy(original)
        working['calibration']=effective(original,self.current_exp)['calibration']
        self.project=working
        try:
            # Base save() writes project state, so use an isolated helper instead.
            self._learn_current_template()
            for key in ('templates','template_history'):original[key]=working.get(key,{})
        finally:self.project=original
        self.save();self.clear_seeds();self.redraw_overlay()

    def _learn_current_template(self):
        from ..measurement.vision import learn_template,learn_color
        from ..measurement.calibration import to_world
        row=self.selected_row();chip=self.chip_choice.currentText()
        if 'rim' not in self.marker_seeds:raise ValueError('가장자리 표시를 먼저 클릭하세요. 안쪽 스티커는 선택 사항입니다.')
        center=np.array(row['raw_center_px']);sample={};colors={}
        height=next((c.get('thickness_m') for c in self.project['chips'] if c['id']==chip),None)
        for role,p in self.marker_seeds.items():
            world=to_world([center,p],self.project['calibration'],height)
            delta=world[1]-world[0] if world is not None else (np.array(p)-center)*[1,-1]
            radius=row.get('radius_m') if world is not None else row['radius_px']
            ratio=float(np.linalg.norm(delta)/max(radius or 1e-9,1e-9))
            if role=='rim' and not .45<ratio<1.3:raise ValueError('가장자리 표시는 칩 바깥 테두리 근처를 클릭하세요.')
            if role=='inner' and ratio<.12:continue  # Centered stickers identify a chip, not its angle.
            sample[role]={'angle':float(np.arctan2(delta[1],delta[0])),'radius_ratio':ratio}
            colors[role]=learn_color(self.original_image,p)
        self.template_samples.setdefault(chip,[]).append(sample)
        if sample.get('inner'):template=learn_template(self.template_samples[chip],self.current_exp['session_id'],colors)
        else:template={'version':1,'session_id':self.current_exp['session_id'],'geometry_status':'rim_only',
            'body_axis':'rim_direction','colors':colors,'rim_radius_ratio':sample['rim']['radius_ratio'],
            'status':'user_confirmed_geometry_not_dynamic_validation'}
        old=self.project['templates'].get(chip);template['version']=(old or {}).get('version',0)+1
        self.project['templates'][chip]=template
        self.project.setdefault('template_history',[]).append({'chip_id':chip,'before':old,'after':template,
            'experiment_id':self.current_exp['id'],'frame':self.current_frame})
        self.review_details.appendPlainText('표식 색상 저장 완료. 보정 반영 재분석을 실행하세요.')

    def grid_click(self,x,y):
        text,ok=QInputDialog.getText(self,'격자 교차점 번호','기준 교차점을 (0,0)으로 잡고 가로 칸 번호, 세로 칸 번호를 입력하세요. 예: 4, 3')
        if not ok:return
        indices=[int(v.strip()) for v in text.split(',')]
        if len(indices)!=2:raise ValueError('칸 번호 두 개를 입력하세요.')
        samples=self.current_exp.setdefault('manual_grid_points',[])
        if any(np.linalg.norm(np.array(s['pixel'])-[x,y])<2 or s['grid']==indices for s in samples):raise ValueError('이미 입력한 교차점입니다.')
        samples.append({'pixel':[x,y],'grid':indices,'frame':self.current_frame})
        self.save()
        self.review_details.appendPlainText(f'격자 점 {len(samples)}개 저장. 넓게 떨어진 4개 이상 + 검사할 별도 점 2개를 찍으세요.')
        if len(samples)>=6:
            choice,ok=QInputDialog.getItem(self,'실제 격자 방향 확인','영상상 가로 칸 번호 방향의 실제 길이 (원근 때문에 화면 픽셀 길이만으로 확정하지 마세요)',
                ['긴 변 43/18 cm','짧은 변 40.5/18 cm','점 계속 추가','이 영상의 수동 점 초기화'],0,False)
            if not ok or choice=='점 계속 추가':return
            if choice=='이 영상의 수동 점 초기화':self.current_exp['manual_grid_points']=[];self.save();return
            from ..measurement.calibration import fit_plane
            short,long=sorted(self.project.get('quick_setup',{}).get('floor_grid_pitches_m',[.405/18,.43/18]))
            sx,sy=(long,short) if choice.startswith('긴') else (short,long)
            px=[s['pixel'] for s in samples];world=[[s['grid'][0]*sx,-s['grid'][1]*sy] for s in samples]
            cal=fit_plane(px[:-2],world[:-2],effective(self.project,self.current_exp)['calibration'],
                holdout={'pixel_points':px[-2:],'world_points':world[-2:]},evidence='user_grid_indices_separate_holdout')
            cal.update(status='provisional',validation_scope='same_grid_consistency_not_independent_accuracy')
            self.current_exp['calibration']=cal;self.current_exp['manual_plane_locked']=True;self.save()
            QMessageBox.information(self,'이 영상 거리 보정 저장',f"입력에 쓰지 않은 격자 점 오차: {cal['holdout_rmse_m']*1000:.2f} mm\n판정: {cal['status']}\n보정 반영 재분석을 실행하세요.")

    def chip_endpoint(self):
        _,frame,chip=self.require_editable_frame()
        choices={'완전히 멈춤 (위치·회전)':'stopped','이동만 멈춤 (회전은 계속)':'translation_stopped',
                 '화면 이탈 직전, 이 장면까지 관측':'exit','실험 바닥 이탈 직전, 이후 마찰 피팅 제외':'surface_exit',
                 '다시 화면에 들어온 첫 장면':'reentry','이 칩의 관측 범위 초기화':'reset','이 칩의 관측·피팅 구간을 표에서 편집':'table'}
        choice,ok=QInputDialog.getItem(self,f'{chip} · 프레임 {frame}','현재 표시된 장면의 의미를 선택하세요.',list(choices),0,False)
        if not ok:return
        if choices[choice]=='table':return self.interval_table(chip)
        trial=copy.deepcopy(self.current_exp);set_endpoint(trial,chip,frame,choices[choice])
        self.current_exp.clear();self.current_exp.update(trial);self.save()
        QMessageBox.information(self,'지정 완료','이 칩에만 저장했습니다. 정지는 관측을 지우지 않습니다.\n보정 반영 재분석 후 피팅·품질 통계에 반영됩니다.')

    def interval_table(self,chip):
        from ..core.review import validate_intervals
        d=QDialog(self);d.setWindowTitle(chip+' 관측·피팅 범위');v=QVBoxLayout(d);d.resize(760,460)
        v.addWidget(QLabel('양 끝 프레임을 포함합니다. 화면 이탈 구간은 줄 사이의 빈 범위로 두세요.\n마찰 피팅을 끄더라도 위치는 저장됩니다. 여러 구간은 겹치지 않게 시간순으로 입력하세요.'))
        t=QTableWidget(0,4);t.setHorizontalHeaderLabels(['첫 프레임','마지막 프레임','바닥 마찰 피팅 사용','근거']);v.addWidget(t)
        segments=self.current_exp.get('chip_intervals',{}).get(chip,[{'start':self.current_exp['interval'][0],'end':self.current_exp['interval'][1]}])
        def add(segment=None):
            segment=segment or {};i=t.rowCount();t.insertRow(i)
            for col,val in [(0,segment.get('start',self.current_frame)),(1,segment.get('end') if segment.get('end') is not None else self.slider.maximum()),(3,segment.get('reason','사용자 지정'))]:t.setItem(i,col,QTableWidgetItem(str(val)))
            check=QCheckBox('사용');check.setChecked(segment.get('fit_enabled',True));t.setCellWidget(i,2,check)
        for s in segments:add(s)
        bar=QHBoxLayout();v.addLayout(bar)
        b=QPushButton('구간 추가');b.clicked.connect(lambda:add());bar.addWidget(b)
        b=QPushButton('선택 구간 삭제');b.clicked.connect(lambda:t.removeRow(t.currentRow()));bar.addWidget(b)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);v.addWidget(buttons);buttons.rejected.connect(d.reject)
        def commit():
            try:
                trial=copy.deepcopy(self.current_exp);parsed=[]
                for i in range(t.rowCount()):
                    start,end=int(t.item(i,0).text()),int(t.item(i,1).text())
                    if start<self.current_exp['interval'][0] or end>self.slider.maximum():raise ValueError('영상의 분석 시작·끝 범위 안에서 지정하세요.')
                    parsed.append({'start':start,'end':end,'fit_enabled':t.cellWidget(i,2).isChecked(),'reason':t.item(i,3).text()})
                trial.setdefault('chip_intervals',{})[chip]=parsed;validate_intervals(trial)
                trial.setdefault('review_history',[]).append({'kind':'interval_table','chip_id':chip,'before':segments,'after':parsed})
                self.current_exp.clear();self.current_exp.update(trial);self.save();d.accept()
            except (ValueError,AttributeError) as exc:QMessageBox.warning(d,'구간 확인',str(exc))
        buttons.accepted.connect(commit);d.exec()

    def boundary_dialog(self):
        self.require_editable_frame();i=self.event_table.currentRow()
        if i<0:raise ValueError('오른쪽 충돌 목록에서 한 충돌을 먼저 선택하세요.')
        event=self.events[i];d=QDialog(self);d.setWindowTitle('충돌 직전·직후의 유효 장면');d.resize(1150,760)
        from .viewer import ImageView,FrameLoader
        from ..core.config import source_path
        layout=QVBoxLayout(d);layout.addWidget(QLabel('왼쪽 = 마지막 충돌 전 / 오른쪽 = 첫 충돌 후. 두 기준 프레임은 보존하고 그 사이만 미분에서 제외합니다.'))
        row=QHBoxLayout();layout.addLayout(row,1);spins=[];loaders=[];loaded=[None,None];tokens=[0,0]
        boundary=event.get('contact_frame_interval') or event.get('boundary_frame_interval') or [event['frame_start'],event['frame_end']]
        for side in range(2):
            box=QVBoxLayout();row.addLayout(box);view=ImageView();view.point_mode=False;box.addWidget(view,1)
            spin=QSpinBox();spin.setKeyboardTracking(False);spin.setRange(0,self.slider.maximum());spin.setValue(int(boundary[side]));spins.append(spin)
            bar=QHBoxLayout();box.addLayout(bar);bar.addWidget(QLabel('충돌 전' if side==0 else '충돌 후'))
            for title,delta in [('◀ 1',-1),('1 ▶',1)]:
                b=QPushButton(title);b.clicked.connect(lambda checked=False,s=spin,n=delta:s.setValue(s.value()+n));bar.addWidget(b)
            bar.addWidget(spin);loader=FrameLoader(d);loaders.append(loader)
            def request(f,s=side,l=loader):
                tokens[s]+=1;loaded[s]=None;l.submit(tokens[s],source_path(self.folder,self.current_exp),f)
            def ready(value,s=side,v=view):
                token,timing,img=value
                if token==tokens[s]:v.set_image(img);loaded[s]=timing['frame_index']
            loader.ready.connect(ready);loader.failed.connect(lambda value:self.statusBar().showMessage(value[1]));spin.valueChanged.connect(request);request(spin.value())
        msg=QLabel('두 화면을 확인하고 저장하세요. 이 작업만으로 충돌 계수 사용 승인이 되지는 않습니다.');layout.addWidget(msg)
        actions=QHBoxLayout();layout.addLayout(actions)
        full=QPushButton('전체화면 / 복원');full.clicked.connect(lambda:d.showNormal() if d.isFullScreen() else d.showFullScreen());actions.addWidget(full)
        commit=QPushButton('이 전후 프레임 저장');actions.addWidget(commit)
        def accept():
            try:
                a,b=[s.value() for s in spins]
                if loaded!=[a,b]:raise ValueError('두 프레임이 모두 표시될 때까지 기다리세요.')
                validate_boundary(a,b)
                self.edit('event',{'contact_frame_interval':[a,b],'unusable_frame_intervals':event.get('unusable_frame_intervals',[]),
                    'review_basis':event.get('review_basis'),'status':'review_required','contact_occurrence':'actual'},
                    '사용자가 원본 전후 장면 확인',frames=[event['frame_start'],event['frame_end']],event_id=event['id'])
                d.accept()
            except ValueError as exc:msg.setText(str(exc))
        commit.clicked.connect(accept);d.finished.connect(lambda _:[l.stop() for l in loaders]);d.exec()

    def review_event(self,approved):
        self.require_editable_frame();i=self.event_table.currentRow()
        if i<0:raise ValueError('충돌 목록에서 하나를 선택하세요.')
        ev=self.events[i]
        if not ev.get('review_basis'):raise ValueError('이전 버전 분석입니다. v5.0에서 보정 반영 재분석 후 확인하세요.')
        after={'review_basis':ev['review_basis']}
        if approved:
            if ev['kind']!='isolated_binary':raise ValueError('전후 측정이 가능한 단독 두 칩 충돌만 계수 계산에 사용할 수 있습니다. 전후 프레임과 추적을 먼저 확인하세요.')
            after.update(status='approved',contact_occurrence='actual')
        else:
            options=['실제 충돌이지만 계수 계산에서 제외','충돌하지 않고 지나감','접촉 여부를 판단할 수 없음']
            choice,ok=QInputDialog.getItem(self,'충돌과 피팅 사용을 따로 구분','분류',options,0,False)
            if not ok:return
            after.update(status='excluded',contact_occurrence=['actual','none','uncertain'][options.index(choice)])
            if choice==options[1]:after['kind']='noncontact_pass'
        reason=self.reason()
        if reason:self.edit('event',after,reason,[ev['frame_start'],ev['frame_end']],event_id=ev['id'])

    def preview_ready(self,value):
        super().preview_ready(value)
        if value[0]==self.preview_token:self.redraw_overlay()

    def redraw_overlay(self):
        if not hasattr(self,'show_markers') or self.original_image is None:return
        import cv2
        img=self.original_image.copy();labels=[]
        for r in self.current_rows:
            if r.get('status')=='outside_interval':continue
            center=tuple(np.round(r['raw_center_px']).astype(int));radius=int(r['radius_px'])
            from ..measurement.overlay import draw_observation
            draw_observation(img,r,markers=False)
            entry=r.get('markers',{}).get(r['chip_id'],{});found=[]
            for role,color in [('rim',(30,220,255)),('inner',(255,160,50))]:
                point=(entry.get(role) or {}).get('point_px') if isinstance(entry.get(role),dict) else None
                if point is not None:
                    ambiguous=entry.get(role+'_ambiguous',False);found.append(('가장자리' if role=='rim' else '안쪽')+(' ?' if ambiguous else ' 확인'))
                    if self.show_markers.isChecked():
                        p=tuple(np.round(point).astype(int));cv2.drawMarker(img,p,color,cv2.MARKER_CROSS,14,2);cv2.line(img,center,p,color,1)
            labels.append(r['chip_id']+': '+(' · '.join(found) or '표식 미검출')+(' · 각도 있음' if r.get('theta_wrapped_rad') is not None else ' · 회전 미측정'))
        self.image_view.set_image(img);self.marker_summary.setText(' | '.join(labels) or '현재 장면에 관측된 칩이 없습니다.')

    def load_review_data(self):
        super().load_review_data()
        for i,event in enumerate(self.events):
            interval=event.get('contact_frame_interval') or event.get('boundary_frame_interval')
            if interval:
                self.event_table.item(i,2).setText(f'{interval[0]} → {interval[1]}')
                self.event_table.item(i,2).setToolTip(f"후보 탐색 범위 {event['frame_start']}–{event['frame_end']} / 표시한 두 프레임은 유효 전후 표본")
        if not self.current_run or self.graph_kind.currentIndex()==1:return
        with Records(self.current_run/'records.sqlite') as db:rows=list(db.rows('trajectories'))
        rows=[r for r in rows if r.get('status') not in ('outside_interval','missing','predicted_only')]
        self.figure.clear();self.cursor_lines=[]
        metric=bool(rows) and all(r.get('world_center_m') is not None for r in rows)
        xy_mode=self.graph_kind.currentIndex()==0
        axes=np.atleast_1d(self.figure.subplots(1 if xy_mode else 3,1))
        for chip in sorted({r['chip_id'] for r in rows}):
            data=[r for r in rows if r['chip_id']==chip];stride=max(1,len(data)//2500);data=data[::stride]
            pos=np.array([r['world_center_m'] if metric else r['raw_center_px'] for r in data])*(100 if metric else 1)
            times=[r.get('physical_time_s') for r in data]
            # Break lines across missing frames or chip re-entry; never imply observed motion through a gap.
            pos=pos.astype(float)
            for j in range(1,len(data)):
                if data[j]['frame_index']-data[j-1]['frame_index']>stride or data[j].get('scope_segment')!=data[j-1].get('scope_segment'):pos[j]=np.nan
            if xy_mode:axes[0].plot(pos[:,0],pos[:,1],label=chip)
            else:
                axes[0].plot(times,pos[:,0],label=chip+' x');axes[0].plot(times,pos[:,1],label=chip+' y',linestyle='--')
            if not xy_mode:
                axes[1].plot(times,[r.get('theta_unwrapped_rad',r.get('theta_wrapped_rad')) if r.get('theta_unwrapped_rad',r.get('theta_wrapped_rad')) is not None else np.nan for r in data],label=chip)
                axes[2].plot(times,[r.get('omega_rad_s') if r.get('omega_rad_s') is not None else np.nan for r in data])
        unit='cm' if metric else 'px (distance uncalibrated)'
        axes[0].set_ylabel('y ('+unit+')' if xy_mode else 'x, y ('+unit+')')
        axes[0].set_xlabel('x ('+unit+')' if xy_mode else 'physical time (s)')
        if xy_mode:
            axes[0].set_aspect('equal',adjustable='datalim')
            if not metric:axes[0].invert_yaxis()
        for ax,y in zip(axes[1:],['angle (rad)','omega (rad/s)']):ax.set_ylabel(y);ax.set_xlabel('physical time (s)')
        for ax in axes:ax.grid(alpha=.2)
        if rows:axes[0].legend(fontsize=7,ncols=2)
        self.canvas.draw_idle()

    def refresh_home(self):
        super().refresh_home()
        if not self.project or not hasattr(self,'cal_state'):return
        experiments=self.project.get('experiments',[])
        valid=sum(e.get('calibration',self.project['calibration']).get('H') is not None and e.get('calibration',self.project['calibration']).get('status') in ('verified','provisional','synthetic') for e in experiments)
        if valid:
            self.cal_state.setText(f'영상별 거리 변환 {valid}/{len(experiments)}개 사용 가능 · 실제 좌표는 결과에서 확인하세요.\n잠정 보정은 독립 실측 정확도 인증이 아닙니다. 미보정 영상만 px 단위로 저장됩니다.')
        elif experiments:self.cal_state.setText('거리 변환을 아직 얻지 못했습니다. 위치는 2차원 픽셀 좌표로 저장됩니다.\n보정 영상 또는 실험 영상의 격자 교차점으로 거리 보정을 확인하세요.')

    def full_review(self):
        if self._full_dialog:return
        host=self.image_view.parentWidget();split=host.parentWidget()
        if not isinstance(split,QSplitter):return
        index=split.indexOf(host);sizes=split.sizes();d=QDialog(self);self._full_dialog=d
        d.setWindowTitle('영상 전체화면 · Esc 닫기');layout=QVBoxLayout(d);bar=QHBoxLayout();layout.addLayout(bar)
        bar.addWidget(QLabel('오른쪽 드래그 이동 · 휠 확대 · 아래 버튼으로 한 프레임씩 이동'))
        chips=QComboBox();chips.addItems([self.chip_choice.itemText(i) for i in range(self.chip_choice.count())]);chips.setCurrentText(self.chip_choice.currentText());chips.currentTextChanged.connect(self.chip_choice.setCurrentText);bar.addWidget(chips)
        modes=QComboBox();modes.addItems([self.click_mode.itemText(i) for i in range(self.click_mode.count())]);modes.setCurrentIndex(self.click_mode.currentIndex());modes.currentIndexChanged.connect(self.click_mode.setCurrentIndex);bar.addWidget(modes)
        close=QPushButton('전체화면 닫기 (Esc)');close.clicked.connect(d.accept);bar.addWidget(close)
        actions=QHBoxLayout();layout.addLayout(actions)
        for title,action in [('표식 클릭 반영',self.correct_marker),('충돌 전후 지정',self.boundary_dialog),('정지·이탈 지정',self.chip_endpoint)]:
            button=QPushButton(title);button.clicked.connect(lambda checked=False,fn=action:self.guarded(fn));actions.addWidget(button)
        layout.addWidget(host,1)
        try:d.showFullScreen();d.exec()
        finally:split.insertWidget(index,host);split.setSizes(sizes);self._full_dialog=None;d.deleteLater()

    def cancel_work(self):
        if self.study_control:self.study_control.cancel()
        elif self.quick_running:self.stop_quick()
        elif self.batch:self.batch.cancel()
        self.work_label.setText('중단 요청 · 현재 계산 경계에서 안전하게 종료합니다.')

    def job_update(self,value):
        super().job_update(value)
        if not hasattr(self,'work_progress'):return
        message=value.get('message') or value.get('stage','작업 중')
        if value.get('stage')=='study':
            elapsed=value.get('elapsed_s',0);calls=value.get('evaluations',0)
            self.work_label.setText(f'{message} · {elapsed:.0f}초 · 모델 평가 {calls}회')
            if value.get('indeterminate'):self.work_progress.setRange(0,0)
            else:
                self.work_progress.setRange(0,100)
                if value.get('overall_percent') is not None:self.work_progress.setValue(round(value['overall_percent']))
        elif self.quick_running:
            self.work_label.setText(self.progress_text.text());self.work_progress.setRange(0,100)
            self.work_progress.setValue(self.progress.value())

    def study_train(self):
        self.require()
        if self.busy or self.quick_running:raise ValueError('진행 중인 작업을 먼저 마치세요.')
        from ..models.study import train_constants
        if not any(e.get('fit_role')=='train' for e in self.project['experiments']):raise ValueError('먼저 계수 구하기용 영상을 지정하세요.')
        self.work_progress.setRange(0,100);self.work_progress.setValue(0)
        self.study_control=Control();folder=self.folder;snapshot=copy.deepcopy(self.project);control=self.study_control
        self.background(lambda:train_constants(folder,snapshot,progress=self.signals.job.emit,control=control),self.study_trained,'공통 계수 계산')

    def show_preflight(self):
        self.require()
        from ..models.study import preflight
        folder=self.folder;snapshot=copy.deepcopy(self.project)
        def done(rows):
            QMessageBox.information(self,'계수용 영상 점검', '\n\n'.join(r['video']+'\n'+r['reason'] for r in rows) or '계수 구하기용 영상을 먼저 지정하세요.')
        self.background(lambda:preflight(folder,snapshot),done,'계수 입력 조건 확인')

    def show_constants(self):
        self.require()
        from ..core.storage import read_json
        if not self.project.get('constant_bank'):raise ValueError('저장한 계수가 없습니다. 계수 구하기를 먼저 실행하세요.')
        bank=read_json(self.folder/self.project['constant_bank']);names={'mu_bottom':'바닥 마찰','e_normal':'법선 반발','e_tangential':'접선 반발','mu_collision':'충돌 마찰'}
        lines=[]
        for key,name in names.items():
            status=bank.get('coefficient_status',{}).get(key,{})
            lines.append(name+': '+(f"{bank['parameters'][key]:.6g}" if key in bank['parameters'] else '계산 보류')+'\n'+status.get('reason','상세 기록 확인'))
        lines.append('숫자가 나왔다는 사실은 정확도 검증이 아닙니다. 저장 계수로 다른 영상을 비교하세요.')
        QMessageBox.information(self,'계수별 상태','\n\n'.join(lines))

    def run_fit(self):
        self.require()
        import json
        from ..models.fitting import fit_dataset
        from ..core.storage import new_id
        from ..core.task import task_scope
        data=json.loads(self.fit_editor.toPlainText());count=self.bootstrap_count.value()
        out=self.folder/'fits'/new_id('fit');self.study_control=Control();control=self.study_control
        def work():
            with task_scope(self.signals.job.emit,control):return fit_dataset(data,out,count)
        def done(result):
            self.last_fit=result;self.fit_result.setPlainText(json.dumps(result,ensure_ascii=False,indent=2))
        self.background(work,done,'상세 피팅·불확실성 계산')

    def study_test(self):
        self.require()
        if self.busy or self.quick_running:raise ValueError('진행 중인 작업을 먼저 마치세요.')
        if not self.project.get('constant_bank'):raise ValueError('계수를 먼저 구하거나 저장된 계수 파일을 연결하세요.')
        from ..models.study import evaluate_fixed
        self.work_progress.setRange(0,100);self.work_progress.setValue(0)
        self.study_control=Control();folder=self.folder;snapshot=copy.deepcopy(self.project);control=self.study_control
        self.background(lambda:evaluate_fixed(folder,snapshot,folder/snapshot['constant_bank'],progress=self.signals.job.emit,control=control),self.study_tested,'고정 계수 검증')

    def study_trained(self,result):
        self.project['constant_bank']=str(Path(result['path']).relative_to(self.folder));self.save();self.refresh_home()
        self.show_constants()

    def task_done(self,value):
        self.study_control=None
        if hasattr(self,'work_progress'):self.work_progress.setRange(0,100);self.work_progress.setValue(100);self.work_label.setText('계산 완료 · 품질 판정은 결과를 확인하세요.')
        return super().task_done(value)

    def task_failed(self,value):
        self.study_control=None
        if hasattr(self,'work_progress'):self.work_progress.setRange(0,100);self.work_progress.setValue(0);self.work_label.setText('작업 중단 또는 실패 · 기록을 확인하세요.')
        return super().task_failed(value)

    def closeEvent(self,event):
        if self.study_control and self.busy:
            self.study_control.cancel();event.ignore();self.statusBar().showMessage('계산 중단 중입니다. 잠시 뒤 다시 닫아주세요.');return
        return super().closeEvent(event)
