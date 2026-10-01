import os,time,csv
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from fractions import Fraction
import av,cv2,numpy as np,pytest
from pokerchip.config import default_project,create_project,register,save_project,ensure_chips
from pokerchip.automatic import BOARD,board_detector,plane_from_board,calibrate_automatic,detect_count,run_automatic
from pokerchip.jobs import Control
from pokerchip.demo import render_disks
from pokerchip.storage import read_json,Records
from pokerchip.selection import confirm_start

ROOT=Path(__file__).resolve().parents[2]

def encode(path,images,rate=30):
    with av.open(str(path),'w') as container:
        stream=None
        for i,image in enumerate(images):
            if stream is None:
                stream=container.add_stream('libx264',rate=rate);stream.width=image.shape[1];stream.height=image.shape[0]
                stream.pix_fmt='yuv420p';stream.options={'crf':'15','preset':'ultrafast'}
            frame=av.VideoFrame.from_ndarray(image,format='bgr24');frame.pts=i;frame.time_base=Fraction(1,rate)
            for packet in stream.encode(frame):container.mux(packet)
        for packet in stream.encode():container.mux(packet)

def board_image(size=(640,480)):
    return cv2.resize(cv2.imread(str(ROOT/'resources/board_reference.png')),size)

def test_pdf_board_exact_preset_and_nominal_plane():
    assert BOARD['squares']==[11,8] and BOARD['square_m']==.015 and BOARD['marker_m']==.011
    image=board_image();b,d=board_detector();corners,ids,mc,mi=d.detectBoard(image)
    assert len(ids)==70 and set(mi.ravel())==set(range(44))
    c=plane_from_board(corners,ids,image_size=[640,480])
    assert c['status']=='provisional' and c['holdout_rmse_m']<.0002
    assert default_project()['chips'][0]['mass_kg']==.012
    assert default_project()['quick_setup']['floor_grid_pitches_m']==pytest.approx([.405/18,.430/18])

def test_floor_confirmation_and_static_segment_required(tmp_path):
    path=tmp_path/'board.mp4';encode(path,(board_image() for _ in range(25)))
    c,_=calibrate_automatic(path,False)
    assert c['status']=='pending' and c['H'] is None
    c,_=calibrate_automatic(path,True)
    assert c['status']=='provisional' and c['lens_status']=='not_corrected'
    assert c['automatic_report']['stable_end']

def test_automatic_six_black_chips_and_generic_sticker(tmp_path):
    centers=[[100,100],[300,100],[500,100],[100,300],[300,300],[500,300]]
    path=tmp_path/'six.mp4';encode(path,(render_disks(centers,[i*.04]*6) for i in range(12)))
    p=default_project();count,_=detect_count(path,p)
    assert count['count']==6 and count['status']=='stable_proposal'
    assert len(ensure_chips(p,6))==6
    from pokerchip.vision import generic_markers,measure,orientation
    image=render_disks([centers[0]],[.4]);cv2.circle(image,tuple(centers[0]),5,(235,90,25),-1)
    d=measure(image,(centers[0],32),{},p['analysis'])
    m=generic_markers(image,d,['chip_6'],{})
    theta,_,_,_=orientation(m['chip_6'],{})
    assert abs(theta-.4)<.04

def test_floor_grid_scale_guard():
    from pokerchip.gridcheck import floor_grid_check
    pitch=.429/18;image=np.full((800,1200,3),225,np.uint8)
    for x in range(20,1200,80):cv2.line(image,(x,0),(x,799),(60,60,60),2)
    for y in range(20,800,80):cv2.line(image,(0,y),(1199,y),(60,60,60),2)
    s=pitch/80;cal={'status':'provisional','H':[[s,0,0],[0,-s,.3],[0,0,1]]}
    assert floor_grid_check(image,cal,pitch)['status']=='consistent'
    cal['H'][0][0]*=1.2;cal['H'][1][1]*=1.2
    assert floor_grid_check(image,cal,pitch)['status']=='scale_mismatch'

def test_rim_paint_touching_colored_wood_not_merged_into_floor():
    from pokerchip.vision import generic_markers,orientation
    image=np.full((220,220,3),(90,170,210),np.uint8)
    cv2.circle(image,(110,110),60,(40,40,40),-1)
    # Deliberately paint to the outer edge so binary saturation joins the floor.
    cv2.circle(image,(164,110),8,(20,20,240),-1)
    cv2.circle(image,(110,110),5,(230,40,20),-1)
    m=generic_markers(image,{'raw_center_px':[110,110],'radius_px':60},['chip_1'],{})
    theta,_,status,_=orientation(m['chip_1'],{})
    assert theta is not None and abs(theta)<.03

def test_automatic_saves_files_without_geometry_and_isolates_bad_file(tmp_path):
    folder=tmp_path/'experiment';p=create_project(folder)
    video=folder/'chips.mp4';encode(video,(render_disks([[180+i,200]],[i*.03]) for i in range(12)))
    exp=register(folder,p,[video,folder/'missing.mp4'],['chip_1'])
    for e in exp:e['count_mode']='auto'
    confirm_start(exp[0],video,0)
    exp[1]['start_selection']={**exp[0]['start_selection']}  # confirmed source was later removed; failure stays isolated
    result=run_automatic(folder,p,Control())
    assert [r['status'] for r in result['results']]==['complete','failed']
    e=result['project']['experiments'][0];assert e['count_proposal']['count']==1
    rows=list(csv.DictReader((folder/'results/전체_운동데이터.csv').open(encoding='utf-8-sig')))
    assert len(rows)==12 and float(rows[-1]['실제 시간(s)'])==pytest.approx(11/240)
    assert any(r['속도 x(px/s)'] for r in rows)
    assert all(not r['중심 x(m)'] for r in rows)
    assert (folder/'results/영상별_요약.xlsx').exists()

def wait(app,condition,timeout=120):
    end=time.monotonic()+timeout
    while not condition() and time.monotonic()<end:app.processEvents();time.sleep(.02)
    assert condition()

def test_v25_actual_gui_one_click_flow_and_popup_palette(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog,QPushButton,QComboBox
    from PySide6.QtGui import QPalette,QColor
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    from pokerchip.gui import MainWindow
    app=QApplication.instance() or QApplication([])
    # Simulate a system palette with white text before launching the fixed theme.
    pal=app.palette();pal.setColor(QPalette.ColorRole.Text,QColor('white'));app.setPalette(pal)
    folder=tmp_path/'gui';folder.mkdir();source=tmp_path/'input.mp4'
    encode(source,(render_disks([[140+i,200]],[i*.03]) for i in range(12)))
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *a,**k:str(folder))
    w=MainWindow();errors=[];w.error=errors.append;w.show();app.processEvents()
    w.add_paths([str(source)]);assert w.intake_table.rowCount()==1
    assert w.nav.count()==3 and w.tabs.currentIndex()==6
    from PySide6.QtWidgets import QGroupBox
    next(g for g in w.findChildren(QGroupBox) if g.title()=='보정 확인란·칩 규격·촬영 설정 펼치기').setChecked(True)
    app.processEvents()
    assert w.video_mode.palette().color(QPalette.ColorRole.Text).lightness()<100
    w.video_mode.showPopup();app.processEvents()
    assert w.video_mode.view().palette().color(QPalette.ColorRole.Text).lightness()<100
    w.video_mode.hidePopup()
    confirm_start(w.project['experiments'][0],source,0);w.save()
    QTest.mouseClick(w.start_button,Qt.MouseButton.LeftButton)
    wait(app,lambda:not w.quick_running and not w.busy)
    assert not errors
    assert w.tabs.currentIndex()==7 and (folder/'results/전체_운동데이터.csv').exists()
    assert w.project['experiments'][0]['status']=='complete'
    w.close();app.processEvents()
