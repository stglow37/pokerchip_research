"""Monotonic stage-weighted completion, not an invented ETA."""
class BatchProgress:
    def __init__(self, callback, total):
        self.callback = callback or (lambda value: None)
        self.total = total
        self.index = 0
        self.experiment = {}
        self.frames = 0
        self.percent = 0.

    def begin(self, index, experiment, frames):
        percent=self.percent if index==self.index and experiment.get('id')==self.experiment.get('id') else 0.
        self.index, self.experiment, self.frames, self.percent = index, experiment, frames, percent
        self.emit({'stage': 'geometry'})

    def emit(self, value):
        stage = value.get('stage', value.get('status', ''))
        start, end = self.experiment.get('interval', [0, None])
        end = min(end, self.frames - 1) if end is not None else self.frames - 1
        f = value.get('frame')
        fraction = max(0., min(1., ((f or 0)-start+1)/max(1, end-start+1)))
        if stage == 'interval': p = 4. + 10.*fraction
        elif stage == 'geometry': p = 4.
        elif stage == 'counting': p = 15. + 10.*fraction
        elif stage == 'detect': p = 25. + 55.*fraction
        elif stage == 'analysis': p = 81.
        elif stage == 'kinematics': p = 83. + 10.*fraction
        elif stage == 'export': p = 95.
        elif stage in ('complete', 'completed_cache', 'failed', 'cancelled'): p = 100.
        else: p = self.percent
        self.percent = max(self.percent, p)
        self.callback({**value, 'experiment_id': self.experiment.get('id'),
            'video_name': self.experiment.get('name'), 'video_index': self.index,
            'video_total': self.total, 'video_percent': round(self.percent, 1),
            'overall_percent': round(100*(self.index-1+self.percent/100)/max(1,self.total),1),
            'progress_basis': 'stage_weighted_not_time_estimate'})
