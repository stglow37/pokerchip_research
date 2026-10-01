"""Single worker, lightweight job metadata, cooperative control and failure isolation."""
import copy
from pathlib import Path
import threading
import time
from .pipeline import analyze,Cancelled
from ..core.storage import atomic_json,read_json,stamp


class Control:
    def __init__(self):
        self.paused=threading.Event();self.cancelled=threading.Event()

    def cancel(self):
        self.cancelled.set();self.paused.clear()

    def pause(self):self.paused.set()

    def resume(self):self.paused.clear()

    def check(self):
        while self.paused.is_set() and not self.cancelled.is_set():
            time.sleep(.08)
        if self.cancelled.is_set():raise Cancelled("사용자가 안전 경계에서 취소했습니다.")


class Batch:
    def __init__(self,folder,project,callback=None):
        self.folder=Path(folder);self.project=copy.deepcopy(project);self.callback=callback
        self.control=Control();self.thread=None;self.results=[]
        self.jobs_path=self.folder/"jobs.json"

    def run(self,ids=None):
        jobs=[e for e in self.project["experiments"] if e.get("kind","experiment")=="experiment" and (ids is None or e["id"] in ids)]
        self.results=[]
        for experiment in jobs:
            if self.control.cancelled.is_set():break
            entry={"experiment_id":experiment["id"],"status":"running","started":stamp()}
            self.results.append(entry);self.save()
            try:
                entry.update(analyze(self.folder,self.project,experiment,self.control,self.emit))
            except Cancelled as exc:
                entry.update(status="cancelled",reason=str(exc));self.save();self.emit(entry);break
            except Exception as exc:
                entry.update(status="failed",reason=str(exc),error_type=type(exc).__name__)
            self.save();self.emit(entry)
        self.emit({"stage":"batch_finished","results":self.results})
        return self.results

    def emit(self,value):
        if self.callback:self.callback(value)

    def save(self):
        atomic_json(self.jobs_path,{"updated":stamp(),"jobs":self.results,"settings_snapshot_policy":"immutable_at_batch_start"})

    def start(self,ids=None):
        if self.thread and self.thread.is_alive():raise RuntimeError("이미 실행 중입니다.")
        self.thread=threading.Thread(target=self.run,args=(ids,),daemon=True,name="pokerchip-single-worker")
        self.thread.start()

    def pause(self):self.control.paused.set()
    def resume(self):self.control.paused.clear()
    def cancel(self):self.control.cancelled.set()
