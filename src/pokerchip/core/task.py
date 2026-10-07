"""Thread-local progress and cooperative cancellation for numerical jobs."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
from scipy.optimize import least_squares as scipy_least_squares

_job=ContextVar('pokerchip_job',default=None)


@contextmanager
def task_scope(progress=None, control=None):
    state={'progress':progress,'control':control,'started':time.monotonic(),'calls':0,'last_emit':0.,'message':'계산 준비','overall_percent':0.,'phase_end_percent':95.}
    token=_job.set(state)
    try:yield state
    finally:_job.reset(token)


def checkpoint(message=None, **details):
    state=_job.get()
    if state is None:return
    if state['control']:state['control'].check()
    if message:state['message']=message
    if 'overall_percent' in details:state['overall_percent']=max(state['overall_percent'],details['overall_percent'])
    if 'phase_end_percent' in details:state['phase_end_percent']=details['phase_end_percent']
    details['overall_percent']=state['overall_percent']
    details['progress_basis']='stage_and_evaluation_budget_not_time'
    if state['progress']:
        state['progress']({'stage':'study','message':state['message'],'elapsed_s':time.monotonic()-state['started'],
            'evaluations':state['calls'],**details})


def least_squares(fun,*args,**kwargs):
    state=_job.get()
    if state is None:return scipy_least_squares(fun,*args,**kwargs)
    checkpoint()
    initial_calls=state['calls'];base=state['overall_percent'];ceiling=state['phase_end_percent']
    def checked(x,*a,**k):
        if state['control']:state['control'].check()
        result=fun(x,*a,**k);state['calls']+=1
        now=time.monotonic()
        if now-state['last_emit']>.3:
            state['last_emit']=now
            budget=max(1,(kwargs.get('max_nfev') or 100)*(len(x)+1))
            fraction=min(.95,(state['calls']-initial_calls)/budget)
            checkpoint(phase='optimization',indeterminate=False,overall_percent=base+(ceiling-base)*fraction)
        if state['control']:state['control'].check()
        return result
    result=scipy_least_squares(checked,*args,**kwargs)
    checkpoint(phase='optimizer_finished',indeterminate=False)
    return result
