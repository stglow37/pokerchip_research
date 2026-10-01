"""Shared, additive review contract. Endpoints are inclusive; stops are annotations."""
import copy
import math
from .storage import digest, stamp


def validate_intervals(experiment):
    begin,limit=experiment.get('interval',[0,None])
    for chip, segments in experiment.get('chip_intervals', {}).items():
        if chip not in experiment['participating_chip_ids']:
            raise ValueError('구간의 칩 번호가 이 영상에 없습니다.')
        if not isinstance(segments,list):
            raise ValueError('칩 구간은 목록이어야 합니다.')
        previous=-1
        for segment in segments:
            if not isinstance(segment,dict):
                raise ValueError('칩 구간 항목은 객체여야 합니다.')
            a,b=segment['start'],segment.get('end')
            if type(a) is not int or a<begin or a<=previous or (b is not None and (type(b) is not int or b<a)):
                raise ValueError('칩 구간은 순서대로, 겹치지 않게 지정하세요.')
            if limit is not None and (b is None or b>limit):
                raise ValueError('칩 구간은 영상의 분석 시작·끝 범위 안이어야 합니다.')
            for key in ('observable','fit_enabled'):
                if key in segment and not isinstance(segment[key],bool):
                    raise ValueError(f'{key}는 true/false여야 합니다.')
            if 'reason' in segment and not isinstance(segment['reason'],str):
                raise ValueError('구간 이유는 문자열이어야 합니다.')
            previous=b if b is not None else math.inf
    return experiment


def scope(experiment, chip, frame):
    segments=experiment.get('chip_intervals',{}).get(chip)
    if segments is None:
        a,b=experiment.get('interval',[0,None]);segments=[{'start':a,'end':b}]
    for s in segments:
        if s['start']<=frame and (s.get('end') is None or frame<=s['end']):
            stopped=any(a.get('chip_id')==chip and a.get('kind')=='stopped' and frame>a['frame'] for a in experiment.get('stop_annotations',[]))
            return {'observable':s.get('observable',True),'fit_enabled':s.get('fit_enabled',True) and not stopped,
                    'scope_reason':s.get('reason','selected_interval'),'scope_segment':s['start']}
    return {'observable':False,'fit_enabled':False,'scope_reason':'outside_selected_interval','scope_segment':None}


def set_endpoint(experiment, chip, frame, kind):
    draft=copy.deepcopy(experiment)
    _set_endpoint(draft,chip,frame,kind)
    experiment.clear();experiment.update(draft)


def _set_endpoint(experiment, chip, frame, kind):
    """Mutate the explicitly selected chip only. Stop never deletes later observations."""
    if chip not in experiment['participating_chip_ids'] or not isinstance(frame,int):raise ValueError('칩/프레임을 확인하세요.')
    begin,end=experiment.get('interval',[0,None])
    if frame<begin or (end is not None and frame>end):raise ValueError('분석 구간 안의 프레임을 선택하세요.')
    experiment.setdefault('review_history',[]).append({'at':stamp(),'chip_id':chip,'kind':kind,'frame':frame,
        'before':copy.deepcopy(experiment.get('chip_intervals',{}).get(chip))})
    if kind in ('stopped','translation_stopped'):
        experiment.setdefault('stop_annotations',[]).append({'chip_id':chip,'frame':frame,'kind':kind,'at':stamp()})
    elif kind=='reset':experiment.setdefault('chip_intervals',{}).pop(chip,None)
    elif kind=='exit':
        segs=experiment.setdefault('chip_intervals',{}).get(chip,[{'start':begin,'end':end,'fit_enabled':True}])
        active=next((i for i,s in enumerate(segs) if s['start']<=frame and (s.get('end') is None or frame<=s['end'])),None)
        if active is None:raise ValueError('관측 구간 안의 마지막 프레임을 선택하세요.')
        # Preserve earlier departures/reentries instead of filling their invisible gaps.
        experiment['chip_intervals'][chip]=segs[:active]+[{**segs[active],'end':frame,'reason':'human_last_visible'}]
    elif kind=='surface_exit':
        segs=experiment.setdefault('chip_intervals',{}).get(chip,[{'start':begin,'end':end,'fit_enabled':True}])
        active=next((i for i,s in enumerate(segs) if s['start']<=frame and (s.get('end') is None or frame<=s['end'])),None)
        if active is None:raise ValueError('관측 구간 안의 바닥 이탈 직전 프레임을 선택하세요.')
        segments=segs[:active]+[{**segs[active],'end':frame,'reason':'experiment_surface'}]
        if end is None or frame<end:segments.append({'start':frame+1,'end':end,'reason':'different_surface','fit_enabled':False})
        experiment.setdefault('chip_intervals',{})[chip]=segments
    elif kind=='reentry':
        segs=experiment.setdefault('chip_intervals',{}).setdefault(chip,[])
        if not segs or segs[-1].get('end') is None or frame<=segs[-1]['end']:raise ValueError('먼저 화면 이탈 구간을 지정하고 그 뒤의 재진입을 선택하세요.')
        segs.append({'start':frame,'end':end,'reason':'human_reentry','fit_enabled':True})
    else:raise ValueError('알 수 없는 구간 작업')
    validate_intervals(experiment)


def event_identity(source_hash, event):
    return 'contact_'+digest({'source':source_hash,'pair':sorted(event['pair']),
                            'anchor_frame':event['closest_frame']})[:20]


def event_source_identity(experiment):
    """Use the confirmed file identity even before the first run is committed."""
    return (experiment.get('source_hash') or
            experiment.get('start_selection',{}).get('source_hash') or
            experiment['id'])


def event_review_basis(event, rows, config):
    fields=('frame_index','chip_id','raw_center_px','world_center_m','theta_wrapped_rad','status','measurement_warning','scope_segment','fit_enabled')
    return digest({'pair':event['pair'],'candidate':[event['frame_start'],event['frame_end']],
        'rows':[{k:r.get(k) for k in fields} for r in rows],
        'time':config['time_profile'],'calibration':config['calibration'],'analysis':config['analysis'],
        'geometry':[{k:c.get(k) for k in ('id','radius_m','radius_sigma_m')} for c in config['chips']]})


def validate_boundary(last_pre, first_post, unusable=()):
    if not isinstance(last_pre,int) or not isinstance(first_post,int) or not 0<=last_pre<first_post:
        raise ValueError('마지막 충돌 전 프레임은 첫 충돌 후 프레임보다 앞이어야 합니다.')
    for a,b in unusable:
        if a>b or a<0:raise ValueError('사용 불가 프레임 범위 오류')
        if a<=last_pre<=b or a<=first_post<=b:raise ValueError('전후 기준 장면은 사용 불가 범위 밖에서 선택하세요.')
    return [last_pre,first_post]
