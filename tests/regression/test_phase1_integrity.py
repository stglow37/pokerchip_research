import copy
import os
from pathlib import Path

import numpy as np
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtWidgets import QApplication

from pokerchip.analysis import apply_corrections,event_barriers
from pokerchip.application.pipeline import code_manifest,stage_keys
from pokerchip.config import default_project
from pokerchip.core.storage import digest
from pokerchip.models import study
from pokerchip.ui.main_window import MainWindow


def experiment(key="exp_a"):
    return dict(id=key,name=key,session_id="session",video_uri="video.mp4",
                participating_chip_ids=["chip_1","chip_2"],interval=[0,None],status="complete")


def test_stage_code_manifests_cover_canonical_dependencies_not_ui():
    measurement=code_manifest("measurement");physics=code_manifest("physics")
    assert "measurement/vision.py" in measurement
    assert "models/physics/ifr.py" in physics
    assert not any(path.startswith("ui/") for path in measurement|physics)


def test_unrelated_video_correction_does_not_invalidate_analysis_key():
    p=default_project();a=experiment("a");b=experiment("b");p["experiments"]=[a,b]
    before=stage_keys(p,a,"source")["analysis"]
    p["corrections"]=[{"id":"edit_b","action":"center","target":{"experiment_id":"b","chip_id":"chip_1","frames":[1,1]},"after":{"point_px":[1,2]},"reason":"test"}]
    p["correction_cursor"]=1
    assert stage_keys(p,a,"source")["analysis"]==before
    p["corrections"][0]["target"]["experiment_id"]="a"
    assert stage_keys(p,a,"source")["analysis"]!=before


def test_reviewed_noncontact_is_not_a_kinematic_barrier():
    events=[
        dict(pair=["chip_1","chip_2"],frame_start=10,frame_end=20,status="excluded",kind="noncontact_pass"),
        dict(pair=["chip_1","chip_2"],frame_start=30,frame_end=40,status="approved",kind="isolated_binary",
             contact_frame_interval=[34,35]),
    ]
    assert event_barriers(events,"chip_1")==[(34.5,34.5)]


def test_refined_boundary_is_used_instead_of_search_bracket():
    event=dict(pair=["chip_1","chip_2"],frame_start=20,frame_end=45,status="review_required",
               kind="isolated_binary",boundary_frame_interval=[31,33],unusable_frame_intervals=[])
    assert event_barriers([event],"chip_1")==[(31.5,32.5)]


def test_explicit_unusable_frames_are_combined_with_contact_boundary():
    event=dict(pair=["chip_1","chip_2"],frame_start=20,frame_end=45,status="approved",
               kind="isolated_binary",contact_frame_interval=[31,33],unusable_frame_intervals=[[28,29],[35,36]])
    assert event_barriers([event],"chip_1")==[(28,29),(31.5,32.5),(35,36)]


def test_center_correction_invalidates_center_relative_orientation():
    p=default_project();row=dict(chip_id="chip_1",frame_index=4,raw_center_px=[10.,10.],status="observed",
        theta_wrapped_rad=.4,theta_sigma_rad=.02,angle_status="measured",measurement_warning="blurred_edge_review",
        markers={"chip_1":{"rim":[12.,10.]}},edge_residual_px=3.)
    edit={"id":"edit","target":{"chip_id":"chip_1","frames":[4,4]},"action":"center",
          "after":{"point_px":[11.,10.],"sigma_px":1.}}
    cal={"status":"verified","H":[[.001,0,0],[0,-.001,0],[0,0,1]]}
    corrected=apply_corrections(row,[edit],cal,p["chips"])
    assert corrected["theta_wrapped_rad"] is None
    assert corrected["measurement_warning"] is None
    assert corrected["superseded_measurement_warning"]=="blurred_edge_review"
    assert corrected["orientation_status"]=="stale_after_center_correction"
    assert corrected["markers"]=={}


def test_position_only_normal_trial_does_not_require_rotation():
    e=experiment();e["impacts_reviewed"]=True
    state=lambda vx:dict(position=[0.,0.],velocity=[vx,0.],theta=None,omega=None,velocity_sigma=[.01,.01])
    event=dict(id="event",kind="isolated_binary",status="approved",pair=["chip_1","chip_2"],normal=[1.,0.],
               pre=[state(1.),state(0.)],post=[state(0.),state(.7)])
    normal,why=study.normal_trials(e,[event])
    assert len(normal)==1 and not why and normal[0]["rotation_required"] is False
    impacts,why=study.impact_trials(default_project(),e,[event])
    assert not impacts and why[0]["coefficient"]=="ifr"


def test_load_video_uses_measurement_snapshot_but_current_physical_values(tmp_path,monkeypatch):
    p=default_project();p["calibration"]["status"]="synthetic"
    e=experiment();p["experiments"]=[e];e["last_run"]="runs/run";e["source_hash"]="source"
    run=tmp_path/e["last_run"];run.mkdir(parents=True)
    measured=copy.deepcopy(p);measured["chips"][0]["mass_kg"]=.012
    current=copy.deepcopy(p);current["chips"][0]["mass_kg"]=.020
    keys=stage_keys(measured,e,"source")
    payloads={
        str(run/"effective_settings.json"):measured,
        str(run/"manifest.json"):{"source_hash":"source","stage_keys":keys,"settings_hash":"measured"},
    }
    monkeypatch.setattr(study,"read_json",lambda path:payloads[str(Path(path))])
    monkeypatch.setattr(study,"effective",lambda project,exp:current)
    monkeypatch.setattr(study,"stage_keys",lambda cfg,exp,source:{"analysis":keys["analysis"]})
    class EmptyRecords:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def rows(self,*args,**kwargs):return iter(())
    monkeypatch.setattr(study,"Records",EmptyRecords)
    cfg,_,_,provenance=study.load_video(tmp_path,current,e)
    assert cfg["chips"][0]["mass_kg"]==.020
    assert cfg["calibration"]==measured["calibration"]
    assert provenance["physical_settings_source"]=="current_project_snapshot"


def test_background_result_is_not_attached_after_settings_change(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    window=MainWindow();window.folder=tmp_path;window.project=default_project()
    context={"id":"job","project_id":window.project["id"],"folder":str(tmp_path.resolve()),
             "settings_hash":digest(window.project),"allow_project_updates":False,"label":"test"}
    window.active_job=context;window.busy=True;called=[];errors=[]
    monkeypatch.setattr(window,"show_error",errors.append)
    window.project["name"]="changed while running"
    window.task_done((context,called.append,{"result":1}))
    assert not called and errors and not window.busy and window.active_job is None
    window.close();app.processEvents()


def test_stale_preview_failure_never_clears_background_busy_state():
    app=QApplication.instance() or QApplication([])
    window=MainWindow();window.preview_token=7;window.busy=True
    before=window.statusBar().currentMessage()
    window.preview_failed((6,"obsolete failure"))
    assert window.busy and window.statusBar().currentMessage()==before
    window.preview_failed((7,"current preview failure"))
    assert window.busy and "불러오지 못했습니다" in window.statusBar().currentMessage()
    window.close();app.processEvents()
