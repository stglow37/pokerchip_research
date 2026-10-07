"""Frame-index prediction for association only; these velocities are NOT physics."""
import numpy as np
from scipy.optimize import linear_sum_assignment
from .vision import orientation
from ..core.config import COLORS


class Tracker:
    def __init__(self, settings, participating, templates, snapshot=None):
        self.settings, self.participating, self.templates = settings, participating, templates
        self.tracks = (snapshot or {}).get("tracks", {})
        self.serial = (snapshot or {}).get("serial", 0)
        self.claimed = set((snapshot or {}).get("claimed", self.tracks.keys()))

    def snapshot(self):
        return {"tracks":self.tracks, "serial":self.serial,"claimed":sorted(self.claimed)}

    def predicted_rois(self, frame):
        result=[]
        for track in self.tracks.values():
            dt=frame-track["last_frame"]
            if dt<=self.settings["max_gap_frames"]:
                result.append((np.array(track["position"])+dt*np.array(track["velocity_px_frame"]),track["radius"]))
        return result

    def update(self, frame, detections):
        def gate(track):
            # Unobserved frames widen association uncertainty. This does not
            # manufacture observations or relax circle/marker quality gates.
            dt=max(1,frame-track['last_frame']);base=self.settings['assignment_gate_px']
            return min(base*np.sqrt(dt),base+3*track['radius'])
        painted=self.settings.get('identity_mode')=='painted_tracks'
        if painted:
            # A hand at the board edge can fit a circle and contain one red
            # patch. It must not become a chip solely through nearest position.
            detections=[d for d in detections if d.get('surface_status')!='floor_boundary' or any(
                f.get('rim') and f.get('inner') and not f.get('rim_ambiguous') and not f.get('inner_ambiguous')
                for f in d.get('markers',{}).values())]
        # Rank confirmed markers and good arcs before imposing participant count.
        detections=sorted(detections,key=lambda d:(
            -sum(bool(f.get("rim") and f.get("inner") and not f.get("rim_ambiguous") and not f.get("inner_ambiguous")) for f in d.get("markers",{}).values()),
            -d.get("visible_arc_fraction",0),d.get("edge_residual_px",1e6)))
        spatial=self.settings.get('identity_mode') in ('spatial_tracks','painted_tracks')
        if spatial and not self.claimed:detections.sort(key=lambda d:(d['raw_center_px'][0],d['raw_center_px'][1]))
        predictions=[]
        keys=[k for k,v in self.tracks.items() if frame-v["last_frame"]<=self.settings["max_gap_frames"]]
        evidence=[]
        for d in detections:
            possible=[]
            for chip,f in d["markers"].items():
                if chip in self.participating and f.get('identity_eligible',True) and f["rim"] and f["inner"] and not f["rim_ambiguous"] and not f["inner_ambiguous"]:
                    theta,sigma,status,used=orientation(f,self.templates.get(chip,{}))
                    if status!="relative_angle_inconsistent":
                        possible.append(chip)
            evidence.append(possible[0] if len(possible)==1 and self.settings.get("identity_mode") not in ("legacy_unknown","spatial_tracks") else None)
        assignments={}
        if keys and detections:
            costs=np.full((len(keys),len(detections)),1e6)
            for a,k in enumerate(keys):
                tr=self.tracks[k]
                dt=frame-tr["last_frame"]
                pred=np.array(tr["position"])+dt*np.array(tr["velocity_px_frame"])
                for b,d in enumerate(detections):
                    distance=np.linalg.norm(pred-d["raw_center_px"])
                    if distance<gate(tr) and not (k in self.participating and evidence[b] and k!=evidence[b]):
                        costs[a,b]=distance + (0 if evidence[b]==k else 8)
            # Private dummy columns allow every track to be unmatched. Without
            # them a rectangular assignment can force an implausible real match.
            extended=np.column_stack([costs,np.full((len(keys),len(keys)),1e6)])
            for a in range(len(keys)):extended[a,len(detections)+a]=gate(self.tracks[keys[a]])+8
            aa,bb=linear_sum_assignment(extended)
            optimum=float(extended[aa,bb].sum())
            for a,b in zip(aa,bb):
                if b<len(detections) and costs[a,b]<1e6:
                    alternative=extended.copy();alternative[a,b]=1e6
                    ar,ac=linear_sum_assignment(alternative)
                    margin=float(alternative[ar,ac].sum()-optimum)
                    ambiguous=margin<self.settings.get("assignment_margin_px",5.)
                    assignments[b]=(keys[a],ambiguous)
        observed=[]
        used=set()
        for index,d in enumerate(detections):
            if len(observed)>=len(self.participating):
                break
            assigned,ambiguous=assignments.get(index,(None,False))
            identified=evidence[index]
            if identified and identified in self.tracks:
                old=self.tracks[identified];dt=frame-old['last_frame']
                expected=np.array(old['position'])+dt*np.array(old['velocity_px_frame'])
                if dt<=self.settings['max_gap_frames'] and np.linalg.norm(expected-d['raw_center_px'])>gate(old):
                    identified=None;assigned=None;ambiguous=True
            if ambiguous and not identified:
                # Do not move a trusted trajectory into an ambiguous detection.
                # Preserve its prediction until marker evidence resolves identity.
                assigned=None
            if painted and not identified and assigned is None:
                # Reacquire a lost painted chip only with both color marks.
                # Unmarked candidates cannot consume a participant slot.
                generic=[k for k,f in d['markers'].items() if k not in self.claimed and f.get('identity_eligible') is False and f.get('rim') and f.get('inner') and not f.get('rim_ambiguous') and not f.get('inner_ambiguous')]
                rim_only=[k for k,f in d['markers'].items() if k not in self.claimed and f.get('identity_eligible',True) and f.get('rim') and not f.get('rim_ambiguous')]
                if generic:assigned=generic[0]
                elif len(rim_only)==1 and d.get('surface_status')=='inside_floor' and not ambiguous:assigned=rim_only[0]
                else:
                    available=[k for k in self.participating if k not in self.claimed]
                    if (available and not ambiguous and d.get('status')=='observed' and
                        d.get('surface_status')=='inside_floor' and d.get('dark_face_contrast',0)>20 and
                        d.get('visible_arc_fraction',0)>=.9):
                        assigned=available[0]  # position track only; physical color identity remains unverified
                    else:continue
                self.claimed.add(assigned)
            if identified and identified not in used:
                if assigned and assigned.startswith("unknown"):
                    self.tracks[identified]=self.tracks.pop(assigned,self.tracks.get(identified,{}))
                assigned=identified
                ambiguous=False
            if assigned is None or assigned in used:
                if len(observed)>=len(self.participating):
                    continue
                available=[k for k in self.participating if k not in self.claimed]
                if spatial and not ambiguous and available:
                    assigned=available[0];self.claimed.add(assigned)
                else:
                    self.serial+=1
                    assigned=f"unknown_{self.serial}"
            used.add(assigned)
            previous=self.tracks.get(assigned)
            velocity=(np.asarray(d["raw_center_px"])-previous["position"])/(frame-previous["last_frame"]) if previous and frame>previous["last_frame"] else np.zeros(2)
            # A blurred, unmarked launcher/hand circle may be spatially close
            # to the last chip position. It must not refresh a trusted track
            # forever and thereby block reacquisition of the real marked chip.
            if not (painted and d.get('measurement_warning') and not identified):
                self.tracks[assigned]={"position":d["raw_center_px"], "velocity_px_frame":velocity.tolist(),
                                       "radius":d["radius_px"], "last_frame":frame}
            theta=sigma=None
            angle_status="missing"
            used_markers=[]
            if assigned in self.participating and assigned in d['markers']:
                theta,sigma,angle_status,used_markers=orientation(d["markers"][assigned],self.templates.get(assigned,{}))
            elif assigned.startswith('unknown'):
                # A local angle can be measured even when physical identity is unresolved.
                viable=[f for f in d['markers'].values() if f.get('rim') and not f.get('rim_ambiguous')]
                if len(viable)==1:
                    theta,sigma,angle_status,used_markers=orientation(viable[0],{})
            observed.append({**d,"frame_index":frame,"chip_id":assigned,"theta_wrapped_rad":theta,
                             "theta_sigma_rad":sigma,"angle_status":angle_status,"marker_used":used_markers,
                             "identity_status":"ambiguous" if ambiguous else "two_marker_confirmed" if identified else "spatial_track_not_marker_identity" if spatial and assigned in self.participating else "temporal_association" if assigned in self.participating else "unknown",
                             "source":"observation", "assignment_ambiguous":ambiguous})
        for k in keys:
            if k not in used and k in self.tracks:
                tr=self.tracks[k]
                position=np.array(tr["position"])+(frame-tr["last_frame"])*np.array(tr["velocity_px_frame"])
                predictions.append({"frame_index":frame,"chip_id":k,"predicted_center_px":position.tolist(),
                                    "status":"predicted_only","source":"tracking_prediction","last_observed_frame":tr["last_frame"]})
        self.tracks={k:v for k,v in self.tracks.items() if frame-v["last_frame"]<=self.settings["max_gap_frames"]}
        return observed,predictions
