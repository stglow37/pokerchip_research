"""Thread-local progress and cooperative cancellation for numerical jobs."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
from scipy.optimize import least_squares as scipy_least_squares

_job=ContextVar('pokerchip_job',default=None)


@contextmanager
def task_scope(progress=None, control=None):
    state={'progress':progress,'control':control,'started':time.monotonic(),'calls':0,'last_emit':0.,'message':'계산 준비'}
    token=_job.set(state)
    try:yield state
    finally:_job.reset(token)


def checkpoint(message=None, **details):
    state=_job.get()
    if state is None:return
    if state['control']:state['control'].check()
    if message:state['message']=message
    if state['progress']:
        state['progress']({'stage':'study','message':state['message'],'elapsed_s':time.monotonic()-state['started'],
            'evaluations':state['calls'],**details})


def least_squares(fun,*args,**kwargs):
    state=_job.get()
    if state is None:return scipy_least_squares(fun,*args,**kwargs)
    checkpoint()
    def checked(x,*a,**k):
        if state['control']:state['control'].check()
        result=fun(x,*a,**k);state['calls']+=1
        now=time.monotonic()
        if now-state['last_emit']>.3:
            state['last_emit']=now;checkpoint(phase='optimization',indeterminate=True)
        if state['control']:state['control'].check()
        return result
    result=scipy_least_squares(checked,*args,**kwargs)
    checkpoint(phase='optimizer_finished',indeterminate=True)
    return result
