"""Shared GUI/CLI engine with stage fingerprints and transactional frame checkpoints."""
from __future__ import annotations
import copy
from itertools import groupby
from pathlib import Path
import shutil
import time
import traceback
import cv2
import numpy as np
import psutil
from .. import __version__
from ..core.config import effective,source_path
from ..core.review import scope,event_identity,event_source_identity,event_review_basis,validate_boundary
from ..core.storage import backup_database,database_ok,Records,atomic_json,read_json,digest,file_hash,new_id,stamp,active_corrections
from ..measurement.video import frames,metadata
from ..core.timebase import TimeProfile
from ..measurement.calibration import check_compatible,drift
from ..measurement.vision import candidates,measure,marker_features,generic_markers
from ..measurement.tracking import Tracker
from ..analysis.kinematics import apply_corrections,pair_candidates,classify_graph,event_barriers,kinematic_at,refine_event,continuous_angle


def sample_rss():
    """Telemetry failure must not abort scientific processing."""
    try:return psutil.Process().memory_info().rss
    except (psutil.Error, OSError):return 0


class Cancelled(Exception):
    """A user cancellation at a safe frame/stage boundary."""


PACKAGE_ROOT=Path(__file__).resolve().parents[1]
CODE_SCOPES={
    # Include shared core primitives conservatively. A false cache miss is
    # preferable to reusing scientific output after relevant code changed.
    "measurement":("__init__.py","core","measurement","application/pipeline.py","application/automatic.py","application/interval_proposal.py"),
    "analysis":("__init__.py","core","analysis","application/pipeline.py"),
    "physics":("__init__.py","core","analysis","models","application/pipeline.py"),
    "export":("__init__.py","core","analysis","models","application/exporting.py","application/delivery.py","application/review_sheet.py"),
}


def code_manifest(scope=None):
    """Return canonical implementation files participating in a stage.

    Compatibility shims and UI code intentionally do not invalidate scientific
    caches. The default digest covers every canonical processing stage.
    """
    names=CODE_SCOPES if scope is None else {scope:CODE_SCOPES[scope]}
    files=set()
    for entries in names.values():
        for entry in entries:
            path=PACKAGE_ROOT/entry
            files.update(path.rglob("*.py") if path.is_dir() else [path])
    return {p.relative_to(PACKAGE_ROOT).as_posix():file_hash(p) for p in sorted(files) if p.exists()}


def code_digest(scope=None):
    return digest(code_manifest(scope))


def experiment_corrections(project,experiment_id):
    return [x for x in active_corrections(project)
            if x.get("target",{}).get("experiment_id") in (None,experiment_id)]


def stage_keys(project,experiment,source_hash):
    a=project["analysis"]
    detector={k:v for k,v in a.items() if k not in ("window_s","min_samples","max_window_samples","omega_bound_rad_s")}
    raw=digest({"source":source_hash,"code":code_digest("measurement"),"calibration":project["calibration"],"templates":project["templates"],
                "chips":[{k:c.get(k) for k in ("id","radius_m","thickness_m","rim_color","inner_color")} for c in project["chips"]],
                "detector":detector,"interval":experiment["interval"],"participants":experiment["participating_chip_ids"]})
    analysis=digest({"raw":raw,"code":code_digest("analysis"),"time":project["time_profile"],"analysis":a,"mode":project["mode"],
                     "excluded_frame_intervals":experiment.get("excluded_frame_intervals",[]),
                     "chip_intervals":experiment.get("chip_intervals",{}),"stop_annotations":experiment.get("stop_annotations",[]),
                     "corrections":experiment_corrections(project,experiment["id"]),"radius_sigma":[c.get("radius_sigma_m") for c in project["chips"]]})
    physics=digest({"analysis":analysis,"code":code_digest("physics"),"physics":project["physics"],"chips":project["chips"],"fit_split":project["fit_split"]})
    identity={k:experiment.get(k) for k in ("id","session_id","name","conditions","capture_mode")}
    return {"raw":raw,"analysis":analysis,"physics":physics,
            "export":digest({"physics":physics,"code":code_digest("export"),"plot":project["plot"],"experiment":identity})}


def analyze(folder,project,experiment,control=None,progress=None):
    from .exporting import export_run
    folder=Path(folder);config=effective(project,experiment)
    source=source_path(folder,experiment)
    source_hash=file_hash(source)
    from ..measurement.selection import require_start
    require_start(project, experiment, source_hash)
    def markers(image,d,height):
        if config['analysis'].get('identity_mode')=='painted_tracks':
            from ..measurement.markers_v3 import painted_markers
            return painted_markers(image,d,experiment['participating_chip_ids'],config['calibration'],height,config['chips'],config['templates'])
        if config['analysis'].get('identity_mode')=='spatial_tracks':
            return generic_markers(image,d,experiment['participating_chip_ids'],config['calibration'],height)
        return marker_features(image,d,config['templates'],config['calibration'],height)
    if experiment.get("source_hash") and experiment["source_hash"]!=source_hash:
        raise ValueError("등록 원본 SHA-256이 바뀌었습니다. 새 실험으로 등록하세요.")
    keys=stage_keys(config,experiment,source_hash)
    def check():
        if control:control.check()
    def report(stage,frame=None):
        if progress:progress({"experiment_id":experiment["id"],"stage":stage,"frame":frame})
    check()
    # A completed exact run can be reused. Every changed dependency yields a new run.
    indexpath=folder/"cache"/(keys["export"]+".run.json")
    if indexpath.exists():
        previous=read_json(indexpath)
        run=folder/previous["run"]
        if (run/"manifest.json").exists() and read_json(run/"manifest.json")["status"]=="complete" and database_ok(run/"records.sqlite"):
            report("completed_cache")
            return {"run":str(run),"status":"complete","cached":True,"source_hash":source_hash}
    run=folder/"runs"/new_id("run");run.mkdir(parents=True)
    manifest={"id":run.name,"experiment_id":experiment["id"],"session_id":experiment["session_id"],
              "source_hash":source_hash,"source_name":source.name,"created":stamp(),"status":"running",
              "code_version":__version__,"code_hash":code_digest(),
              "code_hashes":{scope:code_digest(scope) for scope in CODE_SCOPES},"stage_keys":keys,"seed":config["seed"],
              "mode":config["mode"],"stages":{},"settings_hash":digest(config),"model_version":"farkas_v1_ifr_reconstruction_v2", "software_accuracy_status":"requires_independent_labels"}
    atomic_json(run/"manifest.json",manifest);atomic_json(run/"effective_settings.json",config)
    atomic_json(run/"experiment.json",experiment)
    start=time.perf_counter();peak=sample_rss()
    cache=folder/"cache"/keys["raw"];cache.mkdir(parents=True,exist_ok=True)
    try:
        raw_complete=cache/"complete.json"
        if not raw_complete.exists():
            checkpoint=read_json(cache/"checkpoint.json") if (cache/"checkpoint.json").exists() else {"last_frame":experiment["interval"][0]-1,"tracker":None}
            tracker=Tracker(config["analysis"],experiment["participating_chip_ids"],config["templates"],checkpoint.get("tracker"))
            reference=None;fixed_points=config["calibration"].get("pixel_points")
            heights=[c.get("thickness_m") for c in config["chips"] if c["id"] in experiment["participating_chip_ids"]]
            height=heights[0] if heights and all(h==heights[0] for h in heights) else None
            with Records(cache/"raw.sqlite") as raw:
                for table in ("frames","observations","predictions"):
                    raw.db.execute(f"DELETE FROM {table} WHERE frame>?",(checkpoint["last_frame"],))
                raw.db.commit()
                n=0;last=checkpoint["last_frame"]
                for timing,image in frames(source,start=last+1,end=experiment["interval"][1],max_frame_bytes=config["analysis"]["max_frame_bytes"]):
                    check();f=timing["frame_index"]
                    check_compatible(config["calibration"],(image.shape[1],image.shape[0]),experiment.get("capture_mode",config["calibration"].get("capture_mode","pending")))
                    if image.nbytes*3>config["analysis"]["max_buffer_bytes"]:
                        raise MemoryError("원본/계측 버퍼가 지정 byte 상한을 초과합니다.")
                    roi_candidates=tracker.predicted_rois(f)
                    if f%config["analysis"]["redetect_every"]==0 or not roi_candidates:
                        fresh=candidates(image,config["analysis"]["radius_px"],config["analysis"].get("roi_px"),config["analysis"]["max_candidates"],profile=config["analysis"].get("detector_profile","dark_chip"))
                        # A fresh image center supersedes a stale extrapolated ROI.
                        # Keeping prediction first caused systematic launch misses.
                        roi_candidates=fresh+[q for q in roi_candidates if not any(np.linalg.norm(c[0]-q[0])<.8*min(c[1],q[1]) for c in fresh)]
                    detections=[];rejections={}
                    source_gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY).astype(np.float32)
                    for i,candidate in enumerate(roi_candidates[:config["analysis"]["max_candidates"]]):
                        try:
                            # Unverified proposals are not physical occluders. Nearby
                            # duplicate Hough circles used to erase the real silhouette.
                            d=measure(image,candidate,config["calibration"],config["analysis"],(),height,gray=source_gray)
                            d["markers"]=markers(image,d,height)
                            if not any(np.linalg.norm(np.array(d['raw_center_px'])-q['raw_center_px'])<.65*(d['radius_px']+q['radius_px']) for q in detections):
                                detections.append(d)
                        except (ValueError,np.linalg.LinAlgError) as exc:
                            reason=str(exc);rejections[reason]=rejections.get(reason,0)+1
                            continue
                    observed,predicted=tracker.update(f,detections)
                    for row in observed:
                        chip=next((c for c in config["chips"] if c["id"]==row["chip_id"]),None)
                        if chip and chip.get("thickness_m") is not None and chip["thickness_m"]!=height:
                            updated=measure(image,(row["raw_center_px"],row["radius_px"]),config["calibration"],config["analysis"],height=chip["thickness_m"])
                            updated["markers"]=markers(image,updated,chip["thickness_m"])
                            from ..measurement.vision import orientation
                            theta,sigma,status,used=orientation(updated["markers"][chip["id"]],config["templates"].get(chip["id"],{}))
                            row.update(updated,theta_wrapped_rad=theta,theta_sigma_rad=sigma,angle_status=status,marker_used=used)
                    timing["chip_count_proposal"]=len(detections)
                    timing["candidate_rejection_reasons"]=rejections
                    timing["count_status"]="proposal_requires_participant_review"
                    if fixed_points and f%12==0:
                        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
                        if reference is None:reference=gray.copy()
                        timing["drift"]=drift(reference,gray,fixed_points)
                    raw.put("frames",f,"",timing)
                    for r in observed:raw.put("observations",f,r["chip_id"],r)
                    for r in predicted:raw.put("predictions",f,r["chip_id"],r)
                    n+=1;last=f;peak=max(peak,sample_rss())
                    if n%4==0:report('detect',f)
                    if n%config["analysis"]["chunk_frames"]==0:
                        raw.db.commit()
                        atomic_json(cache/"checkpoint.json",{"last_frame":last,"tracker":tracker.snapshot(),"source_hash":source_hash,"raw_key":keys["raw"]})
                        report("detect",f)
                raw.db.commit()
                atomic_json(cache/"checkpoint.json",{"last_frame":last,"tracker":tracker.snapshot(),"source_hash":source_hash,"raw_key":keys["raw"]})
                if raw.count("frames")==0:raise ValueError("분석 구간에 디코딩된 프레임이 없습니다.")
            atomic_json(raw_complete,{"status":"complete","source_hash":source_hash,"last_frame":last})
        manifest["stages"]["raw"]="complete";report("analysis")
        # Copy only after the raw writer has closed/checkpointed WAL.
        backup_database(cache/"raw.sqlite",run/"records.sqlite")
        analysis_cache=folder/"cache"/(keys["analysis"]+".sqlite")
        if analysis_cache.exists() and database_ok(analysis_cache):
            backup_database(analysis_cache,run/"records.sqlite")
            manifest["stages"]["analysis"]="completed_cache"
        else:
            derive(run/"records.sqlite",config,experiment,check,report)
            backup_database(run/"records.sqlite",analysis_cache)
            manifest["stages"]["analysis"]="complete"
        manifest["source_metadata"]=metadata(source)
        manifest["runtime"]={"elapsed_s":time.perf_counter()-start,"peak_rss_sampled_bytes":max(peak,sample_rss()),
                             "memory_telemetry_status":"available" if peak else "unavailable", "worker_count":1,"frame_buffer_policy":"one_source_frame_plus_bounded_temporaries","resume_policy":"exact_decode_from_start_skip_committed_frames"}
        manifest["status"]="exporting";atomic_json(run/"manifest.json",manifest)
        check();report('export');export_run(run)
        if experiment.get('quick_workflow',False):
            from .review_sheet import save_sheet
            check();save_sheet(source,run)
            from .board_view import save_board_view
            save_board_view(source,run)
        manifest["stages"]["export"]="complete";manifest["status"]="complete";manifest["completed"]=stamp()
        atomic_json(run/"manifest.json",manifest)
        atomic_json(indexpath,{"run":str(run.relative_to(folder))})
        report("complete")
        return {"run":str(run),"status":"complete","cached":False,"source_hash":source_hash}
    except Exception as exc:
        manifest.update(status="cancelled" if isinstance(exc,Cancelled) else "failed",error={"type":type(exc).__name__,"message":str(exc),"traceback":traceback.format_exc()})
        atomic_json(run/"manifest.json",manifest)
        raise


def derive(path,config,experiment,check,report):
    edits=experiment_corrections(config,experiment["id"])
    profile=TimeProfile(config["time_profile"],config["mode"])
    with Records(path) as db:
        previous=None
        # Materialized effective/manual rows make ID exchanges and window lookup unambiguous.
        for frame in db.rows("frames"):
            check();f=frame["frame_index"]
            timing=profile.timing(frame,previous);previous=frame["presentation_time_s"]
            db.put("frames",f,"",timing)
            for raw in db.rows("observations",start=f,end=f):
                row=apply_corrections(raw,edits,config["calibration"],config["chips"])
                row["physical_time_s"]=timing["exposure_midpoint_s"] if timing["exposure_midpoint_s"] is not None else timing["physical_time_s"]
                row["time_status"]=timing["time_status"]
                if not timing["independent_observation"]:row["status"]="missing"
                row.update(scope(experiment,row["chip_id"],f))
                if not row["observable"]:row["status"]="outside_interval"
                db.put("manual",f,row["chip_id"],row)
            for edit in edits:
                if edit["action"]!="insert_observation" or edit["target"].get("frames")!=[f,f]:continue
                chip=edit["target"]["chip_id"];value=edit["after"]
                row={"frame_index":f,"chip_id":chip,"raw_center_px":value["point_px"],"radius_px":value["radius_px"],
                     "status":"observed","source":"manual_corrected","identity_status":"manual_confirmed","assignment_ambiguous":False,
                     "theta_wrapped_rad":None,"theta_sigma_rad":None,"angle_status":"missing","markers":{},"radius_m":None}
                # Reuse the calibrated center uncertainty transform and replay later edits.
                center_edit={**edit,"action":"center"}
                later=edits[edits.index(edit)+1:]
                row=apply_corrections(row,[center_edit]+later,config["calibration"],config["chips"])
                row["physical_time_s"]=timing["exposure_midpoint_s"] if timing["exposure_midpoint_s"] is not None else timing["physical_time_s"]
                row["time_status"]=timing["time_status"]
                if row.get("world_center_m") is not None:
                    props=next(c for c in config["chips"] if c["id"]==chip);row["radius_m"]=props.get("radius_m")
                if not timing["independent_observation"]:row["status"]="missing"
                row.update(scope(experiment,row["chip_id"],f))
                if not row["observable"]:row["status"]="outside_interval"
                db.put("manual",f,row["chip_id"],row)
        db.db.commit()
        groups=((f,list(rows)) for f,rows in groupby(db.rows("manual"),key=lambda r:r["frame_index"]))
        events=[]
        for event in pair_candidates(groups,config["analysis"]):
            event["legacy_id"]=event["id"]
            event["id"]=event_identity(event_source_identity(experiment),event)
            events.append(event)
            if len(events)>10000:raise ValueError("사건 후보 10000개 초과: 분석 구간/ROI를 분할하세요.")
        # User-added contacts are explicit candidate evidence, not invented states.
        for edit in edits:
            if edit['action']!='add_event':continue
            value=edit['after'];pair=value['pair'];anchor=value['closest_frame']
            if any(set(q['pair'])==set(pair) and q['frame_start']<=anchor<=q['frame_end'] for q in events):continue
            ev={**value,'kind':'unmeasurable','status':'review_required','fit_eligible':False,
                'evidence':'human_added_candidate','gap_unit':'m','min_gap':0.}
            ev['id']=event_identity(event_source_identity(experiment),ev);events.append(ev)
        events.sort(key=lambda e:e['closest_frame'])
        from ..analysis.kinematics import suggest_boundary
        prepared=[]
        for event in events:
            check()
            review_rows=[r for chip in event['pair'] for r in db.rows('manual',chip,
                max(0,event['frame_start']-config['analysis']['max_window_samples']),event['frame_end']+config['analysis']['max_window_samples'])]
            basis=event_review_basis(event,review_rows,config)
            matched=[x for x in edits if x['action']=='event' and x['target'].get('event_id')==event['id']]
            valid=[x for x in matched if x['after'].get('review_basis')==basis]
            pending=dict(event)
            for edit in valid:
                pending.update({k:v for k,v in edit['after'].items() if k in
                    ('contact_frame_interval','unusable_frame_intervals','contact_occurrence')})
                if edit['after'].get('kind')=='noncontact_pass':pending['kind']='noncontact_pass'
            if pending.get('contact_frame_interval'):
                validate_boundary(*pending['contact_frame_interval'],pending.get('unusable_frame_intervals',[]))
                if pending['kind'] in ('persistent_contact','near_simultaneous','simultaneous_multi_contact'):pending['kind']='unmeasurable'
            elif pending.get('contact_occurrence')!='none':
                def change_point_rows(chip,start,end):
                    # A second collision must not use the first impulse as its
                    # incoming straight-line motion. Earlier proposals already
                    # exist because candidates are processed chronologically.
                    for prior,*_ in prepared:
                        if chip not in prior['pair'] or prior.get('kind')=='noncontact_pass':continue
                        pb=prior.get('contact_frame_interval') or prior.get('automatic_boundary_proposal')
                        if pb and pb[1]<pending['closest_frame']:start=max(start,pb[1])
                    for future in events:
                        if chip in future['pair'] and future['closest_frame']>pending['closest_frame']:
                            end=min(end,future['closest_frame']-1)
                    return db.rows('manual',chip,start,end)
                proposal=suggest_boundary(pending,change_point_rows)
                if proposal:
                    pending['automatic_boundary_proposal']=proposal
                    # A long distance candidate is not evidence of persistent contact.
                    if pending['kind']=='persistent_contact':pending['kind']='unmeasurable'
            prepared.append((pending,basis,matched,valid,review_rows))
        final_events=[]
        def boundary(e):
            return e.get('contact_frame_interval') or e.get('automatic_boundary_proposal') or [e['frame_start'],e['frame_end']]
        for event,basis,matched,valid_edits,review_rows in prepared:
            check()
            def get_rows(chip,start,end):
                ea,eb=boundary(event)
                for other,*_ in prepared:
                    if other is event or chip not in other['pair'] or other.get('contact_occurrence')=='none' or other.get('kind')=='noncontact_pass':continue
                    oa,ob=boundary(other)
                    if ob<=ea:start=max(start,ob)
                    elif oa>=eb:end=min(end,oa)
                return db.rows('manual',chip,start,end)
            if event.get('kind')=='noncontact_pass' or event.get('contact_occurrence')=='none':
                result={**event,'kind':'noncontact_pass','fit_eligible':False,'status':'excluded'}
            else:result=refine_event(event,get_rows,config['analysis'],config['chips'])
            result['fit_scope_allowed']=all(r.get('fit_enabled',True) for r in review_rows if event['frame_start']<=r['frame_index']<=event['frame_end'])
            result['review_basis']=basis
            for edit in valid_edits:
                result.update({k:v for k,v in edit['after'].items() if k not in ('pre','post','normal','time_s','kind')})
                if edit['after'].get('kind')=='noncontact_pass':result['kind']='noncontact_pass'
                result['review_reason']=edit['reason']
                result['fit_eligible']=result.get('status')=='approved' and result['kind']=='isolated_binary' and result['fit_scope_allowed']
            if matched and not valid_edits:result.update(status='review_required',fit_eligible=False,reason='측정/설정 변경: 충돌을 다시 확인하세요.')
            final_events.append(result)
        classify_graph(final_events,uncertainty_frames=0)
        for event in final_events:
            from ..analysis.kinematics import automatic_impact_gate
            event['automatic_fit_gate']=automatic_impact_gate(event)
            db.put('events',event['closest_frame'],event['id'],event)
        angle_state={}
        for index,row in enumerate(db.rows("manual")):
            if index%100==0:check();report("kinematics",row["frame_index"])
            barriers=event_barriers(final_events,row["chip_id"])
            barriers.extend(experiment.get("excluded_frame_intervals",[]))
            half=config["analysis"]["max_window_samples"]//2
            neighbors=[r for r in db.rows("manual",row["chip_id"],row["frame_index"]-half,row["frame_index"]+half) if r.get("scope_segment")==row.get("scope_segment")]
            result=kinematic_at(row,neighbors,config["analysis"],barriers)
            result['metric_calculation_status']=result['calculation_status']
            # Always export pixel-space derivatives, with the same gap/event gates.
            pixel_rows=[]
            for r in neighbors:
                q=dict(r);q['world_center_m']=r['raw_center_px'];q['covariance_world']=r.get('covariance_px')
                pixel_rows.append(q)
            target=next((r for r in pixel_rows if r['frame_index']==row['frame_index']),None)
            if target:
                pixel=kinematic_at(target,pixel_rows,config['analysis'],barriers)
                result['pixel_calculation_status']=pixel['calculation_status']
                result['pixel_warning_audit']={k:pixel.get(k) for k in ('calculation_warnings','warning_observation_refs','used_observation_refs','warning_observation_count','used_observation_count','warning_observation_fraction','uses_warned_observations')}
                if result.get('world_center_m') is None and pixel['calculation_status'].startswith('computed'):
                    result.update(result['pixel_warning_audit'])
                    result['calculation_status']='partially_computed_with_warnings' if pixel.get('uses_warned_observations') else 'partially_computed'
                for dest,src in [('vx_px_s','vx_m_s'),('vy_px_s','vy_m_s'),('ax_px_s2','ax_m_s2'),('ay_px_s2','ay_m_s2')]:result[dest]=pixel.get(src)
                if result.get('world_center_m') is None and pixel.get('omega_rad_s') is not None:
                    for key in ('omega_rad_s','alpha_rad_s2','theta_unwrapped_rad','omega_sigma_rad_s','angle_status'):result[key]=pixel.get(key)
                    result['angle_geometry']='image_plane_uncorrected'
            result['geometry_status']=config['calibration']['status']
            result['time_status']=config['time_profile']['status']
            result['speed_m_s']=float(np.hypot(result['vx_m_s'],result['vy_m_s'])) if result.get('vx_m_s') is not None else None
            continuous_angle(result,angle_state)
            db.put("trajectories",row["frame_index"],row["chip_id"],result)
        db.db.commit()
