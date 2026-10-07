<!-- V6 DEVELOPMENT -->
# v6 선택 필드

[V6_DATA_ADDITIONS_KO.md](V6_DATA_ADDITIONS_KO.md)에 실제 의존 관측/경고 참조, 구간별·충돌별 계수, 집계·불확실성, 제출·통합 provenance를 정의했다. schema 2.0 및 기존 필드/파일명을 유지한다.

---

<!-- V5 RELEASE -->
# v5 데이터 계약

추가 필드와 자동/수동 구분은 [V5_DATA_ADDITIONS_KO.md](V5_DATA_ADDITIONS_KO.md)가 정본이다. 기존 필드와 v4.5 계약은 보존한다.

---

<!-- V45 RELEASE -->
# v4.5 데이터 사전 추가

[V45_DATA_ADDITIONS_KO.md](V45_DATA_ADDITIONS_KO.md)에 칩별 구간·정지 주석·수동 각도·사건 검토 근거·계수별 상태 및 관측률 분모 변경을 정의했다. 아래 필드는 기본 호환 계약이다.

---

# 데이터·설정 사전

## 저장 구조

```
project.json
jobs.json
runs/run_<id>/
  manifest.json
  effective_settings.json
  experiment.json
  records.sqlite
  export/  (CSV, JSONL, JSON, XLSX, PNG, REPORT_KO.md)
cache/    (단계별 캐시와 raw checkpoint.json)
fits/fit_<id>/dataset.json, fit.json
```

실제 폴더/파일은 수행 단계에 따라 생깁니다. SQLite `observations` 원시값은 수동값으로 덮지 않습니다. `manual`은 수정 적용 후 유효 관측, `predictions`는 영상 추적용 위치 예측, `trajectories`는 분할 운동학, `events`는 접촉 후보/검토 결과입니다. 물리 예측은 simulation/forward_comparison 파일에 별도 저장됩니다. JSONL은 한 줄 한 레코드이며 중첩 공분산·marker·edge·전후 상태를 보존합니다. CSV는 주요 평탄 필드입니다.

## 시간과 좌표

| 필드 | 정의 |
|---|---|
| frame_index | decoded 0-based 원본 프레임 순서 |
| pts / time_base_num,den | 원본 integer PTS와 유리수 time base; fps로 대체하지 않음 |
| presentation_time_s | PTS×time_base인 재생 시각 |
| physical_time_s | 검증된 t(p)로 얻은 물리 시각; 미검증 null |
| exposure_midpoint_s | 노출 기준이 start/end/midpoint로 알려진 경우만 계산 |
| source_frame_type | native/duplicate/interpolated 등 사용자 확인 분류 |
| independent_observation | 독립 관측 채택 여부; 중복 의심만으로 false 강제 안 함 |
| raw_center_px / raw_x_px,raw_y_px | 표시 회전 적용 원본 pixel, y 아래쪽 |
| world_center_m / x_m,y_m | 보정된 world m, y 위쪽 |
| radius_px / radius_m | 적합 경계 반경; 실측 chip library 반지름과 구별 |
| theta_wrapped_rad | rim 방향을 몸체 기준축으로 한 (−π,π] 상당 각도 |
| theta_unwrapped_rad | 유효 연속 구간 내 누적 각, 독립 speed bound 조건부 |
| vx,vy / ax,ay | 각각 m/s, m/s². 필드에는 단위 suffix 포함 |
| omega / alpha | rad/s, rad/s². 반시계 양수 |
| direction_rad | 진행 속도가 오차에 비해 충분할 때만; 정지 근처 null |
| window_s / actual_window_s | 요청 시간 창 / 실제 사용 표본 시간폭 |
| fit_samples / fit_frame_interval | 실제 적합 표본 수 / 프레임 범위 |

CSV 빈칸과 JSON null은 0이 아닙니다. `timebase_unverified`, `calibration_unverified`, `event_or_launch_boundary`, `insufficient_contiguous_samples`, `alias_ambiguous` 등 이유를 함께 확인합니다.

## 관측·품질·사건 상태

| 필드/상태 | 의미 |
|---|---|
| observed / partially_observed | 경계/표식 관측. 품질 보증 확률 아님 |
| low_confidence / missing | 취약하거나 제외된 관측 |
| predicted_only | 과거 위치 기반 추적 예측. 계측/피팅 입력 아님 |
| source | observation / manual_corrected / tracking_prediction 등 출처 |
| identity_status | two_marker_confirmed / temporal_association / unknown / ambiguous |
| edge_residual_px | 경계 circle fit 잔차; 독립 정확도 아님 |
| visible_arc_fraction | 지지 경계가 차지하는 각도 비율 |
| covariance_px / covariance_world | 중심 x,y,반경 3×3 조건부 공분산 |
| condition | 국소 원 피팅 Jacobian 조건 진단 |
| blur_score / clipped_fraction | Laplacian 선명도 / 포화 비율, 휴리스틱 |
| duplicate_suspected / missing_frame_suspected | 시간·영상 품질 의심, 확인 분류와 구별 |
| geometry_status | calibration_unverified / height_unverified / height_corrected |
| fit_eligible | 승인된 isolated_binary 중 피팅에 쓸 수 있는 사건 |
| kind | isolated_binary, near_simultaneous, simultaneous_multi_contact, persistent_contact, out_of_plane_suspected, invalid, unmeasurable |
| status (event) | review_required / approved / excluded |
| frame_start,end / closest_frame | 사건 후보 bracket / 최소 gap 관측 프레임 |
| candidate_frame_interval | 자동 검색 후보 범위. 물리적 접촉 지속시간이 아님 |
| boundary_frame_interval | 전후 독립 적합 사이의 가능한 충돌 경계 프레임 범위 |
| pre_fit_frame_intervals / post_fit_frame_intervals | 칩별 충돌 전·후 상태 적합에 실제 사용한 범위 |
| unusable_frame_intervals | 가림·노출 혼합 등으로 명시적으로 사용하지 않는 범위 |
| time_s / time_interval_s | 한쪽 전후 적합의 접촉 추정 시각 / 조건부 시간 구간 |
| a_m_s / c_m_s | 충돌 전 정상 접근 / 두 spin 포함 접촉 접선 속도 |
| e_n_obs / e_t_obs | 전후 속도비. e_t_obs는 IFR e_t와 다름 |
| impact_parameter_m | 추정 t_c 직전 상대직선 기준의 부호 있는 횡거리 |
| impact_parameter_normalized | 위 값/(R1+R2); 무차원 |
| incidence_rad | atan2(충돌 전 상대 병진 접선속도, 정상접근속도) |
| scattering_rad | 각 칩 충돌 후 병진 속도의 n,t 기준 각; 정지이면 null |
| normal_sigma_rad_approx | 접촉 위치/반지름 오차로 근사한 법선 각 sigma |

사건 프레임 범위는 후보입니다. overlap만으로 고립 접촉을 확정하지 않습니다. 시간 미검증이면 물리 사건시각도 null입니다.
운동학·자유운동 구간 분할에는 검토된 `contact_frame_interval` 또는 자동 정제된 `boundary_frame_interval`과 모든 `unusable_frame_intervals`의 합집합을 사용합니다. 제외된 비접촉 사건은 장벽으로 사용하지 않습니다. 이 필드가 없는 구형 사건만 후보 범위를 보수적으로 사용합니다.

## 중요한 설정

- `time_profile.status`: pending / declared / verified / synthetic_known_clock. declared는 촬영 조건에 따른 잠정 시간이며 독립 검증을 뜻하지 않습니다. synthetic_known_clock는 합성 모드에만 허용하고 verified에는 evidence가 필요합니다.
- `segments`: `{p_start,p_end,t_start,slow_factor}` 목록. 끝 구간 p_end=null. factor 양수, 경계 연속. 원본 capture PTS는 factor1.
- `frame_types`: frame index 문자열→분류. `exposure_s`, `exposure_reference`: 모르면 null/unknown.
- `calibration`: K, distortion, H(pixel undistorted→world), pose_R, pose_t, image_size `[width,height]`, capture_mode, holdout. 완전 기하를 얻기 전 status를 verified로 바꾸지 않음.
- `chips`: mass_kg, radius_m, thickness_m, inertia_kg_m2, inertia_model, radius_sigma_m, radius_status. 명목20mm와 실측 상태를 구별.
- `templates[chip_id]`: delta_inner_minus_rim_rad, rim/inner_radius_ratio, colors의 hue/hue_tolerance/min_saturation/min_value, session_id, sample_count, version. OpenCV hue 0..180 원형 범위.
- `analysis.radius_px`: 후보 최소/최대 반경; `roi_px`: `[x0,y0,x1,y1]` 또는 null. `identity_mode: legacy_unknown`은 구표식 영상의 고정 새 ID 추론을 끔.
- `analysis.window_s`, min_samples, max_window_samples: 운동학 창. `omega_bound_rad_s`: 회전 alias 검증 상한, 없으면 null.
- `analysis.shared_scale_sigma_fraction`, event_clock_sigma_s: 선택적 공통 기하/시계 sigma. 생략 시 조건부 계산에서 0으로 취급되므로 전체오차 검증 주장은 금지.
- `analysis.chunk_frames`, max_frame_bytes, max_buffer_bytes: checkpoint 간격/메모리 제한. 기본 CPU 단일 worker.
- `experiment.time_profile/calibration/analysis/templates`: 해당 필드의 전체 블록을 지정하면 전역 블록 대신 사용합니다(부분 병합 아님). GUI 전역 프로필 변경은 다음 실행에 적용.
- `analysis.dark_face_contrast_min`(기본12), `dark_face_value_max`(기본170): 제공된 검은 칩 면의 내부/주변 밝기 prior. 흰색 칩용 범용 검출기가 아닙니다.
- `physics`: mu_bottom, e_normal, e_tangential, mu_collision, model. configured 값과 fitted 결과를 구별. fits/fit.json이 추정의 근거.
- `fit_split`: unit=session 또는 trial, train/holdout ID 목록. 독립 보류 표본이 없으면 피팅 비교 실행 제한.

## 피팅과 provenance

free trial: id/session_id/source/time_status/geometry_status/body/times/position_angle/sigma/initial_guess. body는 mass/radius/inertia SI, 초기 상태는 `[x,y,vx,vy,theta,omega]`. impact trial: pre/post 2×6, 두 bodies, normal, approved/kind, pre_sigma/post_sigma(normal,vx,vy가 아니라 vx,vy,omega 순서), normal_sigma. 예제 dataset을 참고합니다.

각 run의 manifest는 원본 SHA-256, 전체 canonical 코드 digest와 measurement/analysis/physics/export 단계별 `code_hashes`, 설정/분석/물리/export 단계 key를 기록합니다. UI와 이전 import 호환 shim은 과학 캐시 코드 해시에서 제외합니다. time profile 수정은 raw 경계 캐시 재사용이 가능하지만 운동학/사건은 다시 계산됩니다. 질량/I는 물리 단계, 표식/기하/검출 설정은 raw 단계, plot 옵션은 export 단계에 연결됩니다. 영상별 보정 이력은 해당 영상의 analysis key만 무효화하고, 전역 보정은 모든 관련 영상을 무효화합니다. 보정 이력은 사용자 이유·이전/이후 값·ID·cursor와 함께 저장됩니다. undo 후 새 수정을 하면 폐기된 redo 분기도 audit에 보존합니다.

계수 피팅은 run에 고정된 시간·기하·관측 결과와 현재 프로젝트에서 명시적으로 선택한 질량·반지름·관성·물리 모델을 결합합니다. provenance의 `measurement_settings_hash`, `physics_settings_hash`, `physical_settings_source`로 두 입력을 구분합니다. 위치 기반 `normal_trials`는 회전을 요구하지 않으며, 회전 포함 `impact_trials`는 IFR 전용입니다.

`quality.observed_fraction_all_target_frames`의 분모는 전체 분석 frame×참여 칩 수입니다. 독립 정답 검출 recall이나 계측 정확도가 아닙니다. RMSE/MAE/coverage는 평가 종류·단위·유효값 수와 함께 읽어야 합니다.
