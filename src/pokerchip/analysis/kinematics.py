"""Segmented irregular-time kinematics, one-sided event states and uncertainty."""
from itertools import combinations
import numpy as np
from scipy.optimize import minimize_scalar
from ..measurement.calibration import to_world
from ..measurement.vision import wrap


def local_polynomial(times, values, sigma, target, degree=2):
    t=np.asarray(times,float)-target
    y=np.asarray(values,float)
    one=y.ndim==1
    if one:
        y=y[:,None]
    sigma=np.broadcast_to(np.asarray(sigma,float).reshape(-1,1),y.shape)
    if len(t)<degree+1 or np.any(np.diff(t)<=0) or np.any(sigma<=0):
        raise ValueError("국소 적합에는 고유 증가 timestamp와 양의 sigma가 필요")
    scale=max(float(np.max(abs(t))),1e-9)
    A=np.vander(t/scale,degree+1,increasing=True)
    coeff=[]; uncertainties=[]
    for column in range(y.shape[1]):
        B=A/sigma[:,column,None]
        beta=np.linalg.lstsq(B,y[:,column]/sigma[:,column],rcond=None)[0]
        residual=(A@beta-y[:,column])/sigma[:,column]
        cov=np.linalg.pinv(B.T@B)*max(1.,sum(residual**2)/max(1,len(t)-degree-1))
        multipliers=np.array([1.,1/scale,2/scale**2][:degree+1])
        coeff.append(beta*multipliers)
        uncertainties.append(np.sqrt(np.diag(cov))*multipliers)
    return np.array(coeff).T.squeeze() if one else np.array(coeff).T, np.array(uncertainties).T.squeeze() if one else np.array(uncertainties).T


def apply_corrections(row, edits, calibration, chips):
    out=dict(row)
    for edit in edits:
        target=edit["target"]
        a,b=target.get("frames",[0,2**63-1])
        if not a<=out["frame_index"]<=b:
            continue
        value=edit["after"]
        if edit["action"]=="swap_id":
            first,second=value
            if out["chip_id"] in (first,second):
                out["chip_id"]=second if out["chip_id"]==first else first
                out["source"]="manual_corrected"
        elif target.get("chip_id")==out["chip_id"]:
            if edit["action"]=="set_id":
                out["chip_id"]=value
            elif edit["action"]=="center":
                previous_warning=out.get("measurement_warning")
                out["raw_center_px"]=value["point_px"]
                if value.get("radius_px") is not None:out["radius_px"]=float(value["radius_px"])
                height=next((c.get("thickness_m") for c in chips if c["id"]==out["chip_id"]),None)
                p=to_world([value["point_px"]],calibration,height)
                out["world_center_m"]=p[0].tolist() if p is not None else None
                out["manual_sigma_px"]=value.get("sigma_px",1.)
                out["assignment_ambiguous"]=False
                out["status"]="observed"
                out["covariance_px"]=(np.eye(3)*out["manual_sigma_px"]**2).tolist()
                if p is not None:
                    xy=np.asarray(value["point_px"],float)
                    probes=to_world([xy+[.01,0],xy+[0,.01]],calibration,height)
                    jac=(probes-p[0]).T/.01
                    cov=np.zeros((3,3));cov[:2,:2]=jac@jac.T*out["manual_sigma_px"]**2
                    out["covariance_world"]=cov.tolist()
                # A changed center changes every center-relative marker vector.
                # Preserve the superseded warning for audit, but never present
                # the old angle/marker quality as if it described the correction.
                out["superseded_measurement_warning"]=previous_warning
                out["measurement_warning"]=None
                out["position_status"]="manual_reviewed"
                out["theta_wrapped_rad"]=None
                out["theta_sigma_rad"]=None
                out["angle_status"]="review_required_after_center_correction"
                out["orientation_status"]="stale_after_center_correction"
                out["markers_stale"]=bool(out.get("markers"))
                old_markers=out.get('markers',{})
                out['superseded_markers']=old_markers
                out["markers"]={}
                entry=old_markers.get(out['chip_id'],{})
                rim=entry.get('rim') if isinstance(entry,dict) else None
                if isinstance(rim,dict) and rim.get('point_px') is not None and not entry.get('rim_ambiguous'):
                    out=recompute_manual_rim(out,rim['point_px'],calibration,chips,source='center_recomputed')
                out["edge_residual_px"]=None
                if value.get("fit_residual_px") is not None:out["manual_edge_residual_px"]=float(value["fit_residual_px"])
                out["edge_quality_status"]="not_recomputed_after_manual_center"
                out.pop("edge_points_px",None)
            elif edit["action"]=="angle":
                out["theta_wrapped_rad"]=float(wrap(value["angle_rad"]))
                out["theta_sigma_rad"]=value.get("sigma_rad",.03)
                out["angle_status"]="manual_reviewed"
                out["orientation_status"]="manual_reviewed"
            elif edit['action']=='marker':
                out=recompute_manual_rim(out,value['point_px'],calibration,chips)
            elif edit["action"]=="exclude_observation":
                out["status"]="missing"
            else:
                continue
            out["source"]="manual_corrected"
        else:
            continue
        out.setdefault("correction_ids",[]).append(edit["id"])
    return out


def recompute_manual_rim(row, point, calibration, chips, source='manual_marker'):
    """Recompute the body axis from measured endpoints; never reuse a stale angle."""
    out=dict(row);center=np.asarray(row['raw_center_px'],float);point=np.asarray(point,float)
    length=np.linalg.norm(point-center);radius=row.get('radius_px') or 0
    if length<max(3.,radius*.45) or (radius and length>radius*1.3):return out
    height=next((c.get('thickness_m') for c in chips if c['id']==row['chip_id']),None)
    wp=to_world([center,point],calibration,height)
    delta=wp[1]-wp[0] if wp is not None else (point-center)*[1,-1]
    angle=float(np.arctan2(delta[1],delta[0]))
    out.update(theta_wrapped_rad=angle,theta_sigma_rad=float(max(.01,np.sqrt(2)*row.get('manual_sigma_px',1.)/length)),
        angle_status=source,orientation_status=source,markers_stale=False,
        angle_geometry='world_plane' if wp is not None else 'image_plane_uncorrected')
    out['markers']={row['chip_id']:{'rim':{'point_px':point.tolist(),'angle':angle,'radius_ratio':length/max(radius,1e-9)},
                                    'inner':None,'rim_ambiguous':False}}
    return out


def pair_candidates(frame_groups, settings):
    """Return contiguous proximity/swept brackets; never invent a capture time."""
    previous={}; active={}; serial=0
    for frame,rows in frame_groups:
        current={r["chip_id"]:r for r in rows if r.get("status") not in ("missing","predicted_only","outside_interval")}
        near={}
        for a,b in combinations(sorted(current),2):
            ra,rb=current[a],current[b]
            metric=ra.get("world_center_m") is not None and rb.get("world_center_m") is not None
            key="world_center_m" if metric else "raw_center_px"
            rk="radius_m" if metric else "radius_px"
            delta=np.asarray(rb[key])-ra[key]
            radius=ra[rk]+rb[rk]
            gap=np.linalg.norm(delta)-radius
            sigma=max(radius*.015,1e-6 if metric else .2)
            is_near=gap<max(4*sigma,.22*radius)
            evidence="distance_candidate"
            if a in previous and b in previous and previous[a]["frame_index"]==frame-1 and previous[b]["frame_index"]==frame-1:
                d0=np.array(previous[b][key])-previous[a][key]
                change=delta-d0
                z=np.clip(-d0@change/max(change@change,1e-20),0,1)
                if np.linalg.norm(d0+z*change)<radius+4*sigma:
                    is_near=True; evidence="swept_candidate_not_confirmed_contact"
            if is_near:
                pair=(a,b)
                near[pair]=True
                if pair not in active:
                    serial+=1
                    active[pair]={"id":f"event_{serial}","pair":list(pair),"frame_start":max(0,frame-1),"frame_end":frame,
                                  "candidate_frame_interval":[max(0,frame-1),frame],
                                  "closest_frame":frame,"min_gap":float(gap),"gap_unit":"m" if metric else "px",
                                  "kind":"unmeasurable","status":"review_required","fit_eligible":False,
                                  "evidence":evidence,"time_s":None,"time_interval_s":None,"reason":"전후 상태와 시간/기하 검토 필요"}
                event=active[pair]; event["frame_end"]=frame+1;event["candidate_frame_interval"]=[event["frame_start"],event["frame_end"]]
                if gap<event["min_gap"]:
                    event["closest_frame"]=frame;event["min_gap"]=float(gap)
        for pair in list(active):
            if pair not in near:
                event=active.pop(pair)
                if event["frame_end"]-event["frame_start"]>settings.get("persistent_frames",8):
                    event["kind"]="persistent_contact"
                yield event
        previous=current
    yield from active.values()


def event_barriers(events, chip_id=None, padding=0):
    """Cuts between last-pre/first-post samples; unusable exposures are inclusive."""
    result=[]
    for event in events:
        if chip_id is not None and chip_id not in event.get('pair',[]):continue
        if event.get('kind')=='noncontact_pass' or event.get('contact_occurrence')=='none':continue
        for lo,hi in event.get('unusable_frame_intervals') or []:
            result.append((max(0,lo-padding),hi+padding))
        boundary=event.get('contact_frame_interval') or event.get('boundary_frame_interval')
        if boundary and boundary[0]<boundary[1]:result.append((boundary[0]+.5,boundary[1]-.5))
        else:
            lo,hi=event.get('frame_start'),event.get('frame_end')
            if lo is not None and hi is not None:result.append((max(0,lo-padding),hi+padding))
    return sorted(set(result))


def classify_graph(events, uncertainty_frames=1):
    for i,e in enumerate(events):
        for f in events[i+1:]:
            if not set(e["pair"]) & set(f["pair"]):
                continue
            overlap=min(e["frame_end"],f["frame_end"])-max(e["frame_start"],f["frame_start"])
            if overlap>=-uncertainty_frames:
                kind="simultaneous_multi_contact" if e["closest_frame"]==f["closest_frame"] else "near_simultaneous"
                e.update(kind=kind,fit_eligible=False,reason="접촉 그래프 시간 구간 중첩")
                f.update(kind=kind,fit_eligible=False,reason="접촉 그래프 시간 구간 중첩")
    return events


def kinematic_at(row, neighbors, settings, barriers):
    result={"frame_index":row["frame_index"],"chip_id":row["chip_id"],"source":row.get("source","observation"),
            "raw_center_px":row["raw_center_px"],"world_center_m":row.get("world_center_m"),
            "theta_wrapped_rad":row.get("theta_wrapped_rad"), "physical_time_s":row.get("physical_time_s"),
            "status":row["status"],"identity_status":row.get("identity_status"),"angle_status":row.get("angle_status"),
            "vx_m_s":None,"vy_m_s":None,"ax_m_s2":None,"ay_m_s2":None,"omega_rad_s":None,"alpha_rad_s2":None,
            "theta_unwrapped_rad":None,"direction_rad":None,"fit_samples":0,"window_s":settings["window_s"],
            "reason":None,"segment":0}
    # Keep measurement exclusions available to downstream fitting. Dropping
    # these flags made blurry/ambiguous positions look eligible again.
    for key in ('measurement_warning','assignment_ambiguous','covariance_world','theta_sigma_rad','surface_status','observable','fit_enabled','scope_reason','scope_segment','position_status','orientation_status'):
        result[key]=row.get(key)
    if row.get("assignment_ambiguous") or row.get("measurement_warning") or row["status"] in ("missing","low_confidence","outside_interval"):
        result["reason"]="unreliable_target_observation";return result
    if row.get("physical_time_s") is None or row.get("world_center_m") is None:
        result["reason"]="timebase_unverified" if row.get("physical_time_s") is None else "calibration_unverified"
        return result
    target=row["physical_time_s"]; frame=row["frame_index"]
    lo,hi=-1,2**63
    for a,b in barriers:
        if a<=frame<=b:
            result["reason"]="event_or_launch_boundary";return result
        if b<frame:lo=max(lo,b)
        if a>frame:hi=min(hi,a)
    selected=[r for r in neighbors if lo<r["frame_index"]<hi and r.get("physical_time_s") is not None and
              abs(r["physical_time_s"]-target)<=settings["window_s"]/2 and r.get("world_center_m") is not None and
              r["status"] not in ("missing","low_confidence","outside_interval") and not r.get("assignment_ambiguous") and not r.get("measurement_warning")]
    # Never smooth across a missing observation, even if the requested time window spans it.
    before=[r for r in selected if r["frame_index"]<=frame];after=[r for r in selected if r["frame_index"]>frame]
    connected=[]
    expected=frame
    for r in reversed(before):
        if r["frame_index"]!=expected:break
        connected.append(r);expected-=1
    connected.reverse();expected=frame+1
    for r in after:
        if r["frame_index"]!=expected:break
        connected.append(r);expected+=1
    selected=connected
    result["segment"]=lo+1
    if len(selected)<settings["min_samples"]:
        result["reason"]="insufficient_contiguous_samples";return result
    t=np.array([r["physical_time_s"] for r in selected])
    if np.any(np.diff(t)<=0):
        result["reason"]="nonmonotonic_time";return result
    sigma=[max(1e-6,np.sqrt(np.trace(np.array(r.get("covariance_world") or np.eye(3)*1e-8)[:2,:2])/2)) for r in selected]
    beta,se=local_polynomial(t,[r["world_center_m"] for r in selected],sigma,target)
    result.update(vx_m_s=float(beta[1,0]),vy_m_s=float(beta[1,1]),ax_m_s2=float(beta[2,0]),ay_m_s2=float(beta[2,1]),
                  velocity_sigma_m_s=se[1].tolist(),acceleration_sigma_m_s2=se[2].tolist(),fit_samples=len(t),
                  actual_window_s=float(t[-1]-t[0]),fit_frame_interval=[selected[0]["frame_index"],selected[-1]["frame_index"]])
    if np.linalg.norm(beta[1])>3*np.linalg.norm(se[1]):
        result["direction_rad"]=float(np.arctan2(beta[1,1],beta[1,0]))
    bound=settings.get("omega_bound_rad_s")
    if any(r.get("theta_wrapped_rad") is None for r in selected):
        result["angle_status"]="missing_in_window"
    elif bound is None or np.max(np.diff(t))*bound>=np.pi:
        result["angle_status"]="alias_ambiguous"
    else:
        angles=np.unwrap([r["theta_wrapped_rad"] for r in selected])
        if np.any(abs(np.diff(angles))>bound*np.diff(t)+.05):
            result["angle_status"]="alias_ambiguous"
        else:
            beta,se=local_polynomial(t,angles,[max(.005,r.get("theta_sigma_rad") or .05) for r in selected],target)
            result.update(theta_unwrapped_rad=float(beta[0]),omega_rad_s=float(beta[1]),alpha_rad_s2=float(beta[2]),
                          omega_sigma_rad_s=float(se[1]),angle_status="unwrap_conditional_on_speed_bound")
    return result


def continuous_angle(result, previous):
    """Choose one 2pi gauge per contiguous valid segment; do not bridge gaps."""
    key=result["chip_id"];old=previous.get(key)
    angle=result.get("theta_unwrapped_rad")
    if angle is None:
        previous.pop(key,None)
        return result
    if old and old["frame_index"]+1==result["frame_index"] and old["segment"]==result["segment"]:
        expected=old["theta_unwrapped_rad"]+float(wrap(result["theta_wrapped_rad"]-old["theta_wrapped_rad"]))
        result["theta_unwrapped_rad"]=angle+2*np.pi*round((expected-angle)/(2*np.pi))
    previous[key]=dict(result)
    return result


def suggest_boundary(event,get_rows):
    """Position-only change point proposal; the operator still approves the event.

    Compare two straight short windows with one straight window. Restrict to
    continuous clear observations so an occlusion cannot masquerade as an impulse.
    """
    series=[]
    for chip in event['pair']:
        rr=[r for r in get_rows(chip,max(0,event['frame_start']-8),event['frame_end']+8)
            if r.get('world_center_m') is not None and r.get('physical_time_s') is not None
            and r.get('status')=='observed' and not r.get('assignment_ambiguous') and not r.get('measurement_warning')]
        series.append(rr)
    best=None
    def error(rr):
        t=np.array([r['physical_time_s'] for r in rr]);t-=t[0]
        a=np.column_stack([np.ones(len(t)),t]);xy=np.array([r['world_center_m'] for r in rr])
        return float(np.sum((xy-a@np.linalg.lstsq(a,xy,rcond=None)[0])**2))
    for f in range(event['frame_start'],event['frame_end']):
        cost=baseline=0.;valid=True
        for rr in series:
            left=[r for r in rr if r['frame_index']<=f][-8:];right=[r for r in rr if r['frame_index']>f][:8]
            if len(left)<5 or len(right)<5 or left[-1]['frame_index']!=f or right[0]['frame_index']!=f+1:
                valid=False;break
            whole=left+right
            if any(b['frame_index']!=a['frame_index']+1 for a,b in zip(whole,whole[1:])):valid=False;break
            cost+=error(left)+error(right);baseline+=error(whole)
        if valid and baseline>1e-8 and cost<baseline*.4:
            score=cost/max(1,len(series))
            if best is None or score<best[0]:best=(score,f)
    return [best[1],best[1]+1] if best else None


def refine_event(event, get_rows, settings, chips):
    clear_gap=event.get('gap_unit')=='m' and event.get('min_gap',0) > max(.003, 4*np.sqrt(sum(
        (c.get('radius_sigma_m') or c.get('radius_m',.02)*.02)**2 for c in chips if c['id'] in event['pair'])))
    # A sampled gap alone cannot reject an impact occurring BETWEEN frames.
    # Require an independently quiet target across both sides of the encounter.
    if clear_gap and get_rows is not None and event.get('contact_occurrence')!='actual':
        quiet=False
        for key in event['pair']:
            rr=[r for r in get_rows(key,max(0,event['frame_start']-10),event['frame_end']+10)
                if r.get('world_center_m') is not None and r.get('status')=='observed' and not r.get('assignment_ambiguous') and not r.get('measurement_warning')]
            before=[r for r in rr if r['frame_index']<event['frame_start']]
            after=[r for r in rr if r['frame_index']>event['frame_end']]
            if len(before)>=5 and len(after)>=5:
                xy=np.array([r['world_center_m'] for r in rr])
                quiet |= bool(np.max(np.linalg.norm(xy-np.median(xy,axis=0),axis=1))<.001)
        if quiet:
            return {**event, 'kind':'noncontact_pass', 'status':'excluded', 'fit_eligible':False,
                    'reason':'명확한 중심 간격 + 상대 원판의 전후 정지 유지 · 비접촉 통과 후보',
                    'e_n_obs':None,'e_t_obs':None}
    if event["kind"] in ("simultaneous_multi_contact","near_simultaneous","persistent_contact","out_of_plane_suspected"):
        return event
    frame=event["closest_frame"]
    explicit=event.get("contact_frame_interval")
    if not explicit and event.get('contact_occurrence')!='none':
        explicit=suggest_boundary(event,get_rows)
        if explicit:event={**event,'automatic_boundary_proposal':explicit,'boundary_proposal_method':'clear_position_change_point_requires_review'}
    pre_end=explicit[0] if explicit else event["frame_start"]-1
    post_start=explicit[1] if explicit else event["frame_end"]+1
    unusable=event.get("unusable_frame_intervals",[])
    sides=[]; bounds=[]
    for chip in event["pair"]:
        rows=list(get_rows(chip,max(0,event["frame_start"]-settings["max_window_samples"]),event["frame_end"]+settings["max_window_samples"]))
        valid=[r for r in rows if r.get("physical_time_s") is not None and r.get("world_center_m") is not None and r["status"] not in ("missing","low_confidence","outside_interval") and not r.get("assignment_ambiguous") and not r.get("measurement_warning")]
        before=[r for r in valid if r["frame_index"]<=pre_end and not any(a<=r["frame_index"]<=b for a,b in unusable)]
        after=[r for r in valid if r["frame_index"]>=post_start and not any(a<=r["frame_index"]<=b for a,b in unusable)]
        if len(before)<3 or len(after)<3:
            return {**event,"reason":"시간/기하/고립 전후 표본 부족","kind":"unmeasurable"}
        # One-sided fits must never span an internal missing frame or exceed
        # the configured physical-time window near a collision.
        before=before[-12:];after=after[:12]
        end_time=before[-1]["physical_time_s"];start_time=after[0]["physical_time_s"]
        before=[r for r in before if end_time-r["physical_time_s"]<=settings["window_s"]]
        after=[r for r in after if r["physical_time_s"]-start_time<=settings["window_s"]]
        for i in range(len(before)-1,0,-1):
            if before[i]["frame_index"]!=before[i-1]["frame_index"]+1:before=before[i:];break
        for i in range(1,len(after)):
            if after[i]["frame_index"]!=after[i-1]["frame_index"]+1:after=after[:i];break
        if len(before)<3 or len(after)<3:
            return {**event,"kind":"unmeasurable","reason":"연속된 전후 표본 3개 이상 필요"}
        bounds.append([before[-1]["physical_time_s"],after[0]["physical_time_s"]])
        sides.append((before,after))
    left=max(x[0] for x in bounds);right=min(x[1] for x in bounds)
    if left>=right:
        return {**event,"kind":"invalid","reason":"전후 시간 역행"}
    props=[next((c for c in chips if c["id"]==key),None) for key in event["pair"]]
    if any(p is None or p.get("radius_m") is None for p in props):
        return {**event,"kind":"unmeasurable","reason":"고유 ID/반지름 미확정"}
    radius=sum(p["radius_m"] for p in props)
    def sidefit(rows,t):
        ts=[r["physical_time_s"] for r in rows]
        sig=[max(1e-5,np.sqrt(np.trace(np.array(r.get("covariance_world") or np.eye(3)*1e-8)[:2,:2])/2)) for r in rows]
        return local_polynomial(ts,[r["world_center_m"] for r in rows],sig,t,degree=settings.get('collision_fit_degree',2))
    def loss(t):
        pre=[sidefit(x[0],t)[0][0] for x in sides]
        post=[sidefit(x[1],t)[0][0] for x in sides]
        return (np.linalg.norm(pre[1]-pre[0])-radius)**2+sum(np.sum((a-b)**2) for a,b in zip(pre,post))
    opt=minimize_scalar(loss,bounds=(left,right),method="bounded")
    tc=float(opt.x);pre=[];post=[];uncert=[]
    for before,after in sides:
        for rows,destination in [(before,pre),(after,post)]:
            beta,se=sidefit(rows,tc)
            angles=[r.get("theta_wrapped_rad") for r in rows]
            omega=None;theta=None;omega_sigma=None
            ts=np.array([r["physical_time_s"] for r in rows])
            bound=settings.get("omega_bound_rad_s")
            if all(x is not None for x in angles) and bound is not None and np.max(np.diff(ts))*bound<np.pi:
                unwrapped=np.unwrap(angles)
                if np.all(abs(np.diff(unwrapped))<=bound*np.diff(ts)+.05):
                    ab,ase=local_polynomial(ts,unwrapped,[max(.005,r.get("theta_sigma_rad") or .03) for r in rows],tc)
                    theta=float(ab[0]);omega=float(ab[1]);omega_sigma=float(ase[1])
            destination.append({"position":beta[0].tolist(),"velocity":beta[1].tolist(),"theta":theta,"omega":omega,
                                "position_sigma":se[0].tolist(),"velocity_sigma":se[1].tolist(),"omega_sigma":omega_sigma,
                                "fit_frames":[r["frame_index"] for r in rows]})
            uncert.append(se[0])
    d=np.array(pre[1]["position"])-pre[0]["position"];distance=np.linalg.norm(d)
    if distance<1e-10:return {**event,"kind":"invalid","reason":"추정 중심 중첩"}
    n=d/distance;t=np.array([-n[1],n[0]])
    rel=np.array(pre[0]["velocity"])-pre[1]["velocity"]
    after_rel=np.array(post[0]["velocity"])-post[1]["velocity"]
    a=float(rel@n)
    sigma_g=np.sqrt(sum(np.sum(s*s) for s in uncert)+sum((p.get("radius_sigma_m") or p["radius_m"]*.02)**2 for p in props)+(distance*settings.get("shared_scale_sigma_fraction",0))**2)
    sigma_t=float(np.hypot(sigma_g/max(abs(a),1e-9),settings.get("event_clock_sigma_s",0)))
    c=float(rel@t+sum(p["radius_m"]*s["omega"] for p,s in zip(props,pre))) if all(s["omega"] is not None for s in pre) else None
    cp=float(after_rel@t+sum(p["radius_m"]*s["omega"] for p,s in zip(props,post))) if all(s["omega"] is not None for s in post) else None
    sigma_a=float(np.sqrt(sum(np.sum((np.asarray(v["velocity_sigma"])*n)**2) for v in pre)))
    eligible=a>max(1e-5,3*sigma_a) and abs(distance-radius)<4*sigma_g and float(after_rel@n)<=3*sigma_a
    pre_intervals=[[side[0][0]["frame_index"],side[0][-1]["frame_index"]] for side in sides]
    post_intervals=[[side[1][0]["frame_index"],side[1][-1]["frame_index"]] for side in sides]
    boundary=[max(x[1] for x in pre_intervals),min(x[0] for x in post_intervals)]
    return {**event,"time_s":tc,"time_interval_s":[max(left,tc-2*sigma_t),min(right,tc+2*sigma_t)],
            "time_sigma_s":sigma_t,"time_method":"one_sided_position_continuity_and_contact_minimization",
            "candidate_frame_interval":event.get("candidate_frame_interval",[event["frame_start"],event["frame_end"]]),
            "boundary_frame_interval":boundary,"pre_fit_frame_intervals":pre_intervals,"post_fit_frame_intervals":post_intervals,
            "unusable_frame_intervals":event.get("unusable_frame_intervals",[]),
            "velocity_fit_degree":settings.get('collision_fit_degree',2),
            "velocity_scope":"short_window_linear_extrapolation_floor_acceleration_bias_unmodeled" if settings.get('collision_fit_degree',2)==1 else 'quadratic_one_sided',
            "kind":"isolated_binary" if eligible else "invalid","fit_eligible":False,
            "status":"review_required","reason":"사건 승인 필요" if eligible else "grazing/접촉 기하 불확실",
            "normal":n.tolist(),"tangent":t.tolist(),"contact_point_m":(np.array(pre[0]["position"])+props[0]["radius_m"]*n).tolist(),
            "pre":pre,"post":post,"approach_sigma_m_s":sigma_a,"a_m_s":a,"c_m_s":c,"c_after_m_s":cp,
            "e_n_obs":float(-after_rel@n/a) if eligible and abs(a)>1e-5 else None,"e_t_obs":-cp/c if eligible and c is not None and cp is not None and abs(c)>1e-5 else None,
            "impact_parameter_m":float((d[0]*rel[1]-d[1]*rel[0])/np.linalg.norm(rel)) if np.linalg.norm(rel)>1e-6 else None,
            "impact_parameter_reference":"pre_state_at_estimated_tc", "incidence_rad":float(np.arctan2(rel@t,a)),
            "impact_parameter_normalized":float((d[0]*rel[1]-d[1]*rel[0])/np.linalg.norm(rel)/radius) if np.linalg.norm(rel)>1e-6 else None,
            "normal_sigma_rad_approx":float(sigma_g/distance),
            "shared_scale_sigma_fraction":settings.get("shared_scale_sigma_fraction",0),"event_clock_sigma_s":settings.get("event_clock_sigma_s",0),
            "scattering_rad":[float(np.arctan2(np.array(s["velocity"])@t,np.array(s["velocity"])@n)) if np.linalg.norm(s["velocity"])>1e-5 else None for s in post],
            "uncertainty_kind":"linearized_fit_plus_radius_assumed_if_pending"}


def monte_carlo(function, independent_mean, independent_cov, shared_cov=None, count=200, seed=0):
    rng=np.random.default_rng(seed)
    mean=np.asarray(independent_mean,float)
    independent=rng.multivariate_normal(np.zeros(mean.shape[-1]),independent_cov,size=(count,len(mean)))
    shared=rng.multivariate_normal(np.zeros(mean.shape[-1]),shared_cov,size=count)[:,None,:] if shared_cov is not None else 0
    outputs=[]
    for sample in mean[None,:,:]+independent+shared:
        outputs.append(function(sample))
    values=np.asarray(outputs,float)
    return {"mean":np.nanmean(values,axis=0),"covariance":np.cov(values,rowvar=False),
            "interval95":np.nanquantile(values,[.025,.975],axis=0),"seed":seed,"count":count,
            "method":"shared_session_draw_plus_independent_draws"}
