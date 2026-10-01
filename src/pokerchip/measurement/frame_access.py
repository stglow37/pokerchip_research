"""PTS-validated exact random access; sequential fallback for ambiguous streams.

Index stores display-order PTS, not container frame-count assumptions. A digest
of decoded pixels validates the returned frame, including rotation. Originals
are never transcoded. The cache is disposable, source-content addressed.
"""
from collections import OrderedDict
from pathlib import Path
import hashlib
import tempfile
import av
import numpy as np
from .video import frames, metadata
from ..core.storage import atomic_json, read_json, file_hash


class Superseded(Exception):
    pass


def pixels(frame, stream):
    rotation = int(round(getattr(frame, 'rotation', 0) or float(stream.metadata.get('rotate', 0))))
    if rotation % 90:
        raise ValueError('90도 배수가 아닌 회전은 지원하지 않습니다.')
    image = frame.to_ndarray(format='bgr24')
    return np.ascontiguousarray(np.rot90(image, rotation // 90)) if rotation else image


def checksum(image):
    return hashlib.blake2b(image.tobytes(), digest_size=16).hexdigest()


class IndexedFrameReader:
    def __init__(self, max_bytes=96*1024*1024, cache_dir=None):
        self.limit=max_bytes; self.bytes=0; self.cache=OrderedDict()
        self.path=None; self.index=None; self.fast=True; self.fallback_reason=None
        self.cache_dir=Path(cache_dir or Path(tempfile.gettempdir())/'pokerchip-frame-index-v5')
        self.signature=None

    def close(self):
        self.cache.clear(); self.bytes=0; self.path=None; self.index=None

    def _check(self, cancelled):
        if cancelled and cancelled(): raise Superseded()

    def prepare(self,path,cancelled=None,progress=None):
        self._check(cancelled)
        path=Path(path).resolve(); stat=path.stat()
        sig=(str(path),stat.st_size,stat.st_mtime_ns)
        if sig==self.signature and self.index is not None:return
        self.close(); self.path=str(path); self.fast=True
        source=file_hash(path); dest=self.cache_dir/(source+'.json')
        meta=metadata(path)
        try:
            data=read_json(dest)
            if data['version']!=1 or data['source_hash']!=source or data['metadata']!=meta or not data['complete']:
                raise ValueError('stale index')
            if len(data['frames'])!=data['decoded_count'] or not data['frames']:raise ValueError('incomplete index')
        except (OSError,ValueError,KeyError,TypeError):
            entries=[]; anchors=[]
            # One exact display-order pass. This also establishes actual count.
            # av keyframe metadata is obtained in the same order in a cheap pass.
            with av.open(str(path)) as container:
                stream=container.streams.video[0]; stream.thread_type='SLICE';stream.codec_context.thread_count=2
                for i,frame in enumerate(container.decode(stream)):
                    self._check(cancelled)
                    if frame.key_frame and frame.pts is not None:anchors.append([i,frame.pts])
            for timing,image in frames(path):
                self._check(cancelled)
                entries.append({'timing':timing,'checksum':checksum(image)})
                if progress and len(entries)%16==0:progress(len(entries),meta.get('estimated_frames') or 0)
            if not entries:raise ValueError('디코딩된 프레임이 없습니다.')
            after=path.stat()
            if (after.st_size,after.st_mtime_ns)!=(stat.st_size,stat.st_mtime_ns):
                raise ValueError('색인 작성 중 원본 파일이 변경되었습니다. 다시 여세요.')
            data={'version':1,'complete':True,'source_hash':source,'metadata':meta,
                  'decoded_count':len(entries),'anchors':anchors,'frames':entries}
            self.cache_dir.mkdir(parents=True,exist_ok=True);atomic_json(dest,data)
        self.index=data;self.signature=sig
        pts=[e['timing']['pts'] for e in data['frames']]
        if any(p is None for p in pts) or len(set(pts))!=len(pts):
            self.fast=False;self.fallback_reason='missing_or_duplicate_pts'

    def get(self,path,index,cancelled=None):
        # Show the first scene immediately on a cold, known-length video. The
        # first nonzero jump builds the index on the worker, not the UI thread.
        if index==0 and self.index is None and metadata(path).get('estimated_frames'):
            self._check(cancelled)
            return next(frames(path,end=0))
        self.prepare(path,cancelled)
        if not 0<=index<self.index['decoded_count']:raise IndexError('프레임이 없습니다.')
        self._check(cancelled)
        if index in self.cache:
            self.cache.move_to_end(index);t,img=self.cache[index];return dict(t),img.copy()
        entry=self.index['frames'][index];image=None
        if self.fast:
            anchor=next((a for a in reversed(self.index['anchors']) if a[0]<=index),None)
            if anchor:
                try:
                    with av.open(self.path) as container:
                        stream=container.streams.video[0];stream.thread_type='SLICE';stream.codec_context.thread_count=2
                        container.seek(anchor[1],stream=stream,backward=True,any_frame=False)
                        display=None
                        for frame in container.decode(stream):
                            self._check(cancelled)
                            if display is None:
                                if frame.pts!=anchor[1]:continue
                                display=anchor[0]
                            expected=self.index['frames'][display]['timing']
                            if frame.pts!=expected['pts']:raise ValueError('seek PTS mismatch')
                            if display==index:
                                image=pixels(frame,stream)
                                if checksum(image)!=entry['checksum']:raise ValueError('seek pixel mismatch')
                                break
                            display+=1
                            if display>=self.index['decoded_count']:break
                    if image is None:raise ValueError('anchor not found')
                except Superseded:raise
                except (ValueError,IndexError,av.error.FFmpegError) as exc:
                    self.fast=False;self.fallback_reason=str(exc);image=None
        fallback_timing=None
        if image is None:
            for timing,img in frames(path,end=index):
                self._check(cancelled)
                if timing['frame_index']==index:image=img;fallback_timing=timing;break
        if image is None:raise IndexError('프레임이 없습니다.')
        timing=dict(fallback_timing or entry['timing'])
        if image.nbytes<=self.limit:
            self.cache[index]=(timing,image);self.bytes+=image.nbytes
            while self.bytes>self.limit:
                _,(_,old)=self.cache.popitem(last=False);self.bytes-=old.nbytes
        return dict(timing),image.copy()
