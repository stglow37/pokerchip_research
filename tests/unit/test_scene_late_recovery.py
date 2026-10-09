import numpy as np
from pokerchip.measurement import scene,video

def test_late_unoccluded_geometry_recovers_without_relaxing_gates(monkeypatch):
 monkeypatch.setattr(video,'metadata',lambda p:{'estimated_frames':500})
 monkeypatch.setattr(video,'frames',lambda p,end:(({'frame_index':i},np.full((4,4,3),i,float)) for i in range(end+1)))
 def detect(image,cal,pitches):
  if image[0,0,0]<180:return {'status':'unmeasurable'}
  return {'status':'provisional','long_direction':'image_vertical','calibration':{'H':[[.001,0,0],[0,-.001,0],[0,0,1]],'K':None,'distortion':None}}
 monkeypatch.setattr(scene,'floor_scene',detect)
 result=scene.video_floor_scene('dummy',{})
 assert result['status']=='provisional'
 assert len(result['consensus_frames'])==3
 assert min(result['consensus_frames'])>=180

def test_late_disagreement_never_certifies_geometry(monkeypatch):
 monkeypatch.setattr(video,'metadata',lambda p:{'estimated_frames':500})
 monkeypatch.setattr(video,'frames',lambda p,end:(({'frame_index':i},np.full((4,4,3),i,float)) for i in range(end+1)))
 def detect(image,cal,pitches):
  i=image[0,0,0]
  if i<180:return {'status':'unmeasurable'}
  scale=.001*(1+i/100)
  return {'status':'provisional','long_direction':'image_vertical','calibration':{'H':[[scale,0,0],[0,-scale,0],[0,0,1]],'K':None,'distortion':None}}
 monkeypatch.setattr(scene,'floor_scene',detect)
 assert scene.video_floor_scene('dummy',{})['status']=='unmeasurable'
