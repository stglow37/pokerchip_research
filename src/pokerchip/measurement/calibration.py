"""Intrinsic ChArUco, fixed board homography, drift, independent length and height."""
import cv2
import numpy as np
from ..core.storage import new_id, file_hash
from .video import frames


def transform(points, H):
    p = np.asarray(points, float).reshape(-1, 2)
    q = np.column_stack([p, np.ones(len(p))]) @ np.asarray(H, float).T
    if np.any(abs(q[:,2]) < 1e-12):
        raise ValueError("호모그래피 특이 영역")
    return q[:,:2]/q[:,2,None]


def undistort(points, profile):
    p = np.asarray(points, float).reshape(-1, 2)
    if profile.get("K") is None:
        return p
    K = np.array(profile["K"], float)
    return cv2.undistortPoints(p.reshape(-1,1,2), K, np.asarray(profile.get("distortion") or [], float), P=K).reshape(-1,2)


def to_world(points, profile, height=None):
    if profile.get("status") not in ("verified", "synthetic", "provisional") or profile.get("H") is None:
        return None
    p = undistort(points, profile)
    if height is not None and profile.get("pose_R") is not None and profile.get("K") is not None:
        K, R, t = np.asarray(profile["K"]), np.asarray(profile["pose_R"]), np.asarray(profile["pose_t"])
        camera = -R.T@t
        rays = np.column_stack([p, np.ones(len(p))])@np.linalg.inv(K).T@R
        if np.any(abs(rays[:,2]) < 1e-10):
            raise ValueError("광선과 높이 평면이 평행")
        factors = (height-camera[2])/rays[:,2]
        if np.any(factors <= 0):
            raise ValueError("카메라 뒤쪽의 높이 평면")
        return (camera + factors[:,None]*rays)[:,:2]
    return transform(p, profile["H"])


def to_pixel(points, profile, height=0.):
    p = np.asarray(points, float).reshape(-1,2)
    if profile.get("pose_R") is not None and profile.get("K") is not None:
        xyz = np.column_stack([p, np.full(len(p), height or 0.)])
        rv = cv2.Rodrigues(np.array(profile["pose_R"], float))[0]
        return cv2.projectPoints(xyz, rv, np.array(profile["pose_t"], float), np.array(profile["K"], float),
                                 np.asarray(profile.get("distortion") or [], float))[0].reshape(-1,2)
    p = transform(p, np.linalg.inv(profile["H"]))
    if profile.get("K") is not None:
        K = np.array(profile["K"], float)
        rays = np.column_stack([p, np.ones(len(p))])@np.linalg.inv(K).T
        p = cv2.projectPoints(rays, np.zeros(3), np.zeros(3), K,
                              np.asarray(profile.get("distortion") or [], float))[0].reshape(-1,2)
    return p


def fit_plane(pixel_points, world_points, base=None, holdout=None, independent_lengths=None, evidence=""):
    base = dict(base or {})
    px, world = np.asarray(pixel_points, float), np.asarray(world_points, float)
    if px.shape != world.shape or len(px) < 4 or px.shape[1] != 2:
        raise ValueError("4개 이상의 pixel/world 대응점 필요")
    up = undistort(px, base)
    H, mask = cv2.findHomography(up, world, cv2.RANSAC, .001)
    if H is None or not np.isfinite(H).all() or np.linalg.cond(H) > 1e12:
        raise ValueError("대응점이 퇴화하거나 변환 불안정")
    residual = np.linalg.norm(transform(up, H)-world, axis=1)
    result = {**base, "id": new_id("plane"), "H": H.tolist(), "status": "pending",
              "fixed_H": True, "train_rmse_m": float(np.sqrt(np.mean(residual[mask.ravel()>0]**2))),
              "inliers": mask.ravel().tolist(), "evidence": evidence,
              "pixel_points": px.tolist(), "world_points": world.tolist(),
              "height_status": "unknown_unless_pose_and_thickness", "holdout_rmse_m": None}
    if base.get("K") is not None:
        xyz = np.column_stack([world, np.zeros(len(world))])
        ok, rv, tv = cv2.solvePnP(xyz, px, np.array(base["K"], float), np.asarray(base.get("distortion") or [], float))
        if ok:
            result.update(pose_R=cv2.Rodrigues(rv)[0].tolist(), pose_t=tv.ravel().tolist())
    if holdout:
        hp = np.asarray(holdout["pixel_points"], float)
        hw = np.asarray(holdout["world_points"], float)
        # A user cannot relabel fitted points as independent holdout points.
        if any(np.min(np.linalg.norm(px-p, axis=1)) < .01 for p in hp):
            raise ValueError("holdout 점이 학습 대응점과 중복됩니다.")
        result["holdout_rmse_m"] = float(np.sqrt(np.mean(np.sum((transform(undistort(hp,base),H)-hw)**2, axis=1))))
    lengths = []
    for pair in independent_lengths or []:
        q = transform(undistort(pair["pixels"], base), H)
        measured = float(np.linalg.norm(q[1]-q[0]))
        if not np.isfinite(pair["known_m"]) or pair["known_m"] <= 0:
            raise ValueError("독립 기준 길이는 양수여야 합니다.")
        lengths.append({"known_m": pair["known_m"], "measured_m": measured, "error_m": measured-pair["known_m"]})
    result["independent_lengths"] = lengths
    from ..analysis.quality import calibration_gate
    result["validation"] = calibration_gate(result)
    result["status"] = "verified" if result["validation"]["passed"] else "pending"
    return result


def grid_points(image, pattern, mask=None):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if mask is not None:
        gray = gray.copy()
        gray[np.asarray(mask, bool)] = 127
    ok, corners = cv2.findChessboardCornersSB(gray, tuple(pattern), flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    return corners.reshape(-1,2) if ok else np.empty((0,2))


def drift(reference_gray, current_gray, fixed_points):
    p = np.asarray(fixed_points, np.float32).reshape(-1,1,2)
    nxt, ok, _ = cv2.calcOpticalFlowPyrLK(reference_gray, current_gray, p, None)
    if nxt is None:
        return {"status": "unmeasurable", "median_drift_px": None}
    back, valid, _ = cv2.calcOpticalFlowPyrLK(current_gray, reference_gray, nxt, None)
    good = (ok.ravel()>0) & (valid.ravel()>0) & (np.linalg.norm(back-p,axis=2).ravel()<1)
    if good.sum() < 4:
        return {"status": "unmeasurable", "median_drift_px": None}
    offset = float(np.median(np.linalg.norm(nxt[good]-p[good],axis=2)))
    return {"status": "drift_suspected" if offset > 1 else "stable", "median_drift_px": offset, "points": int(good.sum()), "H_updated": False}


def calibrate_views(objects, images, size, holdout_indices):
    held = set(holdout_indices)
    train = [i for i in range(len(images)) if i not in held]
    if len(train) < 6 or not held:
        raise ValueError("6개 이상 학습 pose와 별도 holdout pose가 필요합니다.")
    obj = [np.asarray(x,np.float32) for x in objects]
    img = [np.asarray(x,np.float32).reshape(-1,1,2) for x in images]
    rms,K,d,rv,tv = cv2.calibrateCamera([obj[i] for i in train], [img[i] for i in train], tuple(size), None, None)
    errors = []
    for i in sorted(held):
        ids = np.arange(len(obj[i]))
        pose_ids, test_ids = ids[::2], ids[1::2]
        if len(pose_ids) < 6 or len(test_ids) < 4:
            continue
        ok,r,t = cv2.solvePnP(obj[i][pose_ids], img[i][pose_ids], K,d)
        if ok:
            pred = cv2.projectPoints(obj[i][test_ids],r,t,K,d)[0]
            errors.extend(np.linalg.norm(pred-img[i][test_ids],axis=2).ravel().tolist())
    if not errors:
        raise ValueError("holdout pose/검증점이 부족합니다.")
    return {"id": new_id("intrinsic"), "K": K.tolist(), "distortion": d.ravel().tolist(),
            "image_size": list(size), "train_rms_px": float(rms), "holdout_rms_px": float(np.sqrt(np.mean(np.square(errors)))),
            "holdout_indices": sorted(held), "train_indices": train, "status": "pending_plane",
            "intrinsic_status": "fitted_requires_review", "H": None,
            "holdout_method": "pose_on_even_corners_error_on_odd_corners"}


def charuco_video(path, board_spec, capture_mode, stride=12, max_views=80):
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, board_spec.get("dictionary", "DICT_4X4_50")))
    board = cv2.aruco.CharucoBoard(tuple(board_spec["squares"]), board_spec["square_m"], board_spec["marker_m"], dictionary)
    detector = cv2.aruco.CharucoDetector(board)
    objects, images, poses, selected_frames = [], [], [], []
    size = None
    for timing, image in frames(path):
        if timing["frame_index"] % stride:
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        corners, ids, _, _ = detector.detectBoard(gray)
        if ids is None or len(ids) < 12 or cv2.Laplacian(gray,cv2.CV_64F).var() < 20:
            continue
        p = corners.reshape(-1,2)
        # Geometric frame selection: centroid, projected extent and skew of the board.
        feature = np.r_[p.mean(0)/[image.shape[1],image.shape[0]], p.std(0)/[image.shape[1],image.shape[0]]]
        if poses and min(np.linalg.norm(feature-q) for q in poses) < .035:
            continue
        poses.append(feature)
        selected_frames.append(timing["frame_index"])
        objects.append(board.getChessboardCorners()[ids.ravel()])
        images.append(p)
        size = (image.shape[1],image.shape[0])
        if len(images) >= max_views:
            break
    held = list(range(3, len(images), 4))
    result = calibrate_views(objects, images, size, held)
    result.update(board=board_spec, source_hash=file_hash(path), selected_frames=selected_frames, capture_mode=capture_mode,
                  observations=[{"object_points": o.tolist(), "image_points": p.tolist()} for o,p in zip(objects,images)])
    return result


def check_compatible(profile, image_size, capture_mode):
    if profile.get("image_size") and list(image_size) != profile["image_size"]:
        raise ValueError("calibration 해상도/표시방향 불일치")
    if profile.get("capture_mode") not in (None,"pending",capture_mode):
        raise ValueError("calibration 촬영 모드 불일치")
