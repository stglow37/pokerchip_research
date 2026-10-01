"""Human-selected release boundary; never infer consent from an old interval."""
from ..core.storage import stamp, file_hash


def confirm_start(experiment, path, frame, end=None):
    if not isinstance(frame, int) or frame < 0 or (end is not None and end < frame):
        raise ValueError('시작·끝 프레임 범위를 확인하세요.')
    import copy
    previous=copy.deepcopy(experiment.get('chip_intervals',{}))
    if previous:
        experiment.setdefault('review_history',[]).append({'kind':'global_interval_changed','before':previous})
        for key,segs in previous.items():
            result=[]
            for seg in segs:
                a=max(frame,seg['start']);b=seg.get('end')
                if end is not None:b=min(b,end) if b is not None else end
                if b is None or a<=b:result.append({**seg,'start':a,'end':b})
            experiment['chip_intervals'][key]=result
    experiment['interval'] = [frame, end]
    experiment['start_selection'] = dict(frame=frame, end=end, confirmed=True,
        method='human_release_frame', source_hash=file_hash(path), selected_at=stamp(),
        statement='손·고무줄에서 벗어나 원판과 표식을 볼 수 있는 분석 시작 프레임')
    experiment['status'] = 'pending'
    experiment['impacts_reviewed'] = False


def require_start(project, experiment, source_hash=None):
    if project.get('mode') == 'synthetic_demo':
        return
    s = experiment.get('start_selection', {})
    if s.get('method')=='automatic_image_interval':
        proposal=experiment.get('interval_proposal',{})
        if (s.get('proposal_id')==proposal.get('id') and s.get('source_hash') and
            s.get('source_hash')==proposal.get('source_hash') and
            [s.get('frame'),s.get('end')]==experiment.get('interval') and
            (source_hash is None or source_hash==s.get('source_hash'))):return
        raise ValueError('자동 구간의 원본 또는 적용 범위가 바뀌었습니다. 다시 분석하세요.')
    if not (s.get('confirmed') is True and s.get('method') == 'human_release_frame'
            and s.get('frame') == experiment.get('interval', [None])[0]
            and s.get('end') == experiment.get('interval', [None, None])[1]
            and s.get('source_hash')):
        raise ValueError(experiment.get('name', '영상') + ': 사람이 분석 시작 프레임을 선택·확인해야 합니다.')
    if source_hash is not None and s['source_hash'] != source_hash:
        raise ValueError('시작 프레임을 확인한 원본과 현재 영상이 다릅니다. 다시 선택하세요.')
