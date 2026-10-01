from pathlib import Path
import argparse,json,html,base64,collections,datetime,sys
parser=argparse.ArgumentParser(description='검증 요약과 선별 증거에서 v4 보고서를 생성합니다.')
parser.add_argument('--summaries',required=True,type=Path)
parser.add_argument('--evidence',required=True,type=Path)
parser.add_argument('--output-dir',required=True,type=Path)
args=parser.parse_args();root=args.summaries.resolve();evidence=args.evidence.resolve();out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
rows=json.loads((root/'all_results.json').read_text(encoding='utf-8'));ex=[r for r in rows if r['kind']=='experiment'];cal=[r for r in rows if r['kind']=='calibration']
B='v35_default';V='v4_calibrated';parts=[];md=[]
def h(s,n=2):parts.append(f'<h{n}>{html.escape(s)}</h{n}>');md.append('#'*n+' '+s+'\n')
def p(s,kind=''):parts.append(f'<p class="{kind}">{html.escape(s)}</p>');md.append(s+'\n')
def table(headers,data):
 parts.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+html.escape(str(v))+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in data)+'</tbody></table></div>')
 md.append('| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(str(v).replace('|','/') for v in r)+' |' for r in data)+'\n')
def fig(name,cap):
 fp=evidence/name
 if not fp.exists():return
 mime='image/png' if fp.suffix=='.png' else 'image/jpeg';src='data:'+mime+';base64,'+base64.b64encode(fp.read_bytes()).decode()
 parts.append('<figure><img src="'+src+'" alt="'+html.escape(cap)+'"><figcaption>'+html.escape(cap)+'</figcaption></figure>');md.append(f'![{cap}](../evidence/{name})\n')
def number(x,d=0):return '—' if x is None else f'{x:,.{d}f}'
def stat(prefix,key):return sum(r.get(prefix+'_'+key,0) or 0 for r in ex)
status=lambda pref:dict(collections.Counter(r.get(pref+'_status','미실행') for r in ex))
h('PokerChip Astra v4 — 실제 영상 검증 보고서',1)
p('검증 대상: 첨부 PokerChip_Astra_v3.5.zip 및 지정 Google Drive 폴더의 모든 영상. 보고서 생성: '+datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M KST'))
p('실제 영상을 전체 프레임 단위로 실행하면서 추적 누락·개수 추정·좌표 변환·속도 및 회전·충돌 후보·결과 저장·GUI 동작을 검사하고 v4를 수정했습니다. 소프트웨어 실행 완료와 물리 실험의 정확도 인증은 서로 다른 판정입니다.','lead')
h('1. 검증 범위와 핵심 결과')
table(['항목','실행 범위 / 결과'],[
 ['원본 영상',f"51개, {sum(r['frames'] for r in rows):,}프레임, 1,203,010,842바이트. 공급자 파일 크기와 다운로드 크기 일치"],
 ['실험 영상',f"49개: 한 칩 18개, 두 칩 25개, 세 칩 6개. 합계 {sum(r['frames'] for r in ex):,}프레임"],
 ['보정 영상','2개 모두 끝까지 처리. 서로 다른 촬영 세션의 렌즈 보정을 분리 적용'],
 ['v3.5 기본 조건',str(status(B))],['v4 + 해당 세션 렌즈 보정',str(status(V))],
 ['참여 칩 개수 불일치',f"v3.5 기본 조건 {sum(bool(r.get(B+'_count_mismatch')) for r in ex)}개 / v4 {sum(bool(r.get(V+'_count_mismatch')) for r in ex)}개"],
 ['계량 좌표 변환 생성',f"v3.5 기본 조건 {sum(r.get(B+'_geometry_status')=='provisional' for r in ex)}/49, v4 {sum(r.get(V+'_geometry_status')=='provisional' for r in ex)}/49 — 잠정 격자 좌표"],
 ['회귀 테스트','동결 v4 기준 104개 통과. validation/test-records/v4의 로그 및 XML. Qt 실제 클릭·프레임 구간 선택 별도 검증'],
 ['물리 모델 외부 영상 적용','203246에서 적합한 마찰계수를 203310에 고정 적용: 위치 RMSE 8.16 mm, 회전각 RMSE 20.79°']])
p('가장 확실한 추적 결함은 204126의 세 번째 칩 누락입니다. 같은 렌즈 보정을 적용한 v3.5에서도 두 개로 판정했고, v4에서는 세 개를 추적했습니다. 반면 일부 격자·개수 오류는 보정 영상을 넣으면 v3.5에서도 해소됩니다. 보정 입력 효과를 코드 개선 효과와 합쳐 주장하지 않았습니다.')
h('2. 비교 방법과 판정 기준')
p('v3.5 기본 배치는 원본 과학 계산 코드를 유지하고 렌즈 보정이 없는 초기 설정으로 49개 실험을 실행했습니다. 이 실행 환경에서 psutil 프로세스 조회가 실패하므로 v3.5 배치 도구에만 메모리 통계 수집 우회를 적용했습니다. 추적·기하·운동학 계산은 수정하지 않았습니다. v4 배치는 각 촬영 세션의 보정 영상에서 추정한 K와 왜곡계수를 사용하고 실험 영상별 바닥 격자 H를 다시 계산했습니다.')
p('추가로 204126과 203502는 동일한 렌즈 보정을 넣은 v3.5 전체 실행을 수행했습니다. 203825와 203834는 v4와 동일한 바닥 기하를 넣고 v3.5 개수 탐색을 따로 검사했습니다. 203132도 올바른 렌즈 보정 상태에서 실패를 재현했습니다. 따라서 기본 배치의 두 버전 간 수치 차이 전체를 코드 수정만의 효과로 해석하면 안 됩니다.')
p('전체 녹화 시험에는 발사 전 손 접촉, 발사기 가림, 화면 밖 이동, 실험 후 재접촉이 포함됩니다. 배치 검사 도구는 이를 명시한 audit_full_recording 범위로 실행했습니다. 이는 사람의 자유운동 시작 승인을 대신하지 않습니다. 실제 배포 GUI의 시작 프레임 확인 조건은 유지했습니다.')
p('사람이 모든 프레임의 정답 중심·각도를 라벨링한 검증은 아닙니다. 모든 프레임을 프로그램으로 처리하고, 전체 영상의 표본 사진·관측 시트와 주요 실패/충돌 구간을 눈으로 대조했습니다. 관측 비율, 원 테두리 잔차, 보정판 재투영 잔차는 독립 정답 기준의 검출 정답률이나 절대 거리 정확도가 아닙니다.','note')
h('3. 실제 영상에서 확인한 문제와 수정')
table(['문제','원인과 증거','v4 조치 / 남은 한계'],[
 ['세 번째 칩 전체 누락','204126: 원본 방식은 동시에 검출된 최대 개수를 중심으로 판정. 세 칩이 동시에 안정적으로 보이는 표본이 부족해 2개로 제한','반복된 두 색 표식 ID의 합집합 반영. 같은 렌즈 조건에서 2→3개'],
 ['짧은 가시 구간을 놓치는 개수 탐색','203132: 보정 후에도 24개 표본에서 0개. 표본을 192개로 늘리면 같은 품질 기준으로 1개 탐색','최초 0개인 경우에만 192개 표본 재탐색. 실제 구간의 불량 관측을 임의로 정상화하지 않음'],
 ['일부 기본 조건의 격자/개수 오류','렌즈 왜곡이 보정되지 않은 격자선이 정밀 선별 기준에서 탈락. 203825·203834는 v3.5도 올바른 기하에서 2개 탐색','보정 입력 안내와 실패 사유 보존. 격자 정밀도 임계값을 느슨하게 바꾸지 않음'],
 ['참여 ID를 첫 N개로만 선택','자동 개수 판정 이후 실제 색 표식과 무관하게 chip_1부터 배정','반복 확인된 실제 ID를 먼저 선택하고 나머지만 미확정 슬롯으로 채움'],
 ['손·발사기에 추적이 고착','203502·203916: 흐린 무표식 후보가 last_frame과 예측 위치를 계속 갱신해 실제 칩의 표식 재획득을 차단','두 표식 확인 없이 흐림 경고가 있으면 신뢰 추적 상태를 갱신하지 않음. 마지막 전체 배치로 재검증'],
 ['흐린 관측이 속도/회전 계산을 오염','경고 필드는 존재해도 대상 또는 이웃의 흐린 표본이 미분 창 및 사건 적합에 포함','대상·이웃·충돌 전후·자유운동 적합에서 제외. 데이터가 부족하면 빈값 유지'],
 ['중단 버튼 예외','GUI는 Control.cancel()을 호출하지만 원본 Control에는 메서드가 없음','cancel/pause/resume 추가. 중단 시 pause 해제. 실제 Qt 버튼 클릭 검증'],
 ['결과 저장 단계 DB 읽기 실패','203542·203558·203801에서 database disk image is malformed. 원시/분석 캐시와 결과 DB 상태가 다름','백업 API·연결 명시적 종료·읽기 전용 접근·완료 JSONL로 출력. 초기 v4에서도 두 건 재현되어 추가 수정. 환경별 손상의 유일 원인은 확정하지 못함'],
 ['실행 환경 통계 오류로 분석 중단','psutil.Process().memory_info() 예외가 분석 시작/진행 경로로 전파','메모리 통계 unavailable로 기록하고 측정 지속'],
 ['시작 프레임 이후 확인 사진 불일치','사진 선택이 실제 프레임 번호 대신 0~관측 행 수에 의존','저장된 실제 프레임 인덱스 기반 선택'],
 ['구간·검토 GUI의 불편','종료 프레임 제한이 없고 여러 영상 추가/추적 영상 내보내기 접근성이 낮음','종료 프레임, 폴더 추가, 추적 표시 영상 저장, 상태 안내, 테이블 갱신 빈도 개선']])
p('저장 문제의 남은 한계: 최종 고정 코드 배치에서도 200141 영상에서 결과 DB 읽기 손상이 1회 발생했습니다. 원시 DB와 분석 캐시는 무결성 검사를 통과했고, 코드를 바꾸지 않은 재실행으로 결과를 복구했습니다. 표의 최종 완료 상태에는 이 재시도가 포함됩니다. Python 표준 SQLite만 사용하는 별도 40회 검사에서는 문제가 재현되지 않았으므로, 간헐 손상의 유일한 원인은 아직 확정하지 못했습니다. 저장 문제가 완전히 사라졌다는 결론은 내리지 않습니다.','note')
h('3.1 같은 보정 조건의 세 칩 대조',3)
fig('controlled_204126_f258.jpg','204126의 프레임 258. 좌측 v3.5와 우측 v4는 동일한 렌즈 보정값을 사용했습니다. v4가 아래쪽 초록 표식 칩을 포함합니다.')
table(['204126 / 동일 렌즈','v3.5','v4'],[['참여 칩','2','3'],['관측 행 수','695','1,008'],['속도 계산 행 수','677','947'],['각속도 계산 행 수','665','947']])
p('행 수는 칩×프레임 단위입니다. 참여 칩 수가 달라 분모가 바뀌므로 위 증가량을 정확도 향상률로 바꿔 쓰면 안 됩니다. v4가 찾은 충돌 후보는 chip_1–chip_2의 256~260프레임(최접근 258), chip_2–chip_3의 273~278프레임(최접근 275)입니다. 두 사건 모두 신뢰할 수 있는 전후 표본이 부족하여 충돌계수 확정 대상에서 제외되었습니다.')
h('3.2 영상 203132의 탐색 누락',3)
fig('203132_f240.jpg','203132의 240프레임 원본 일부. 이동 중 테두리 흐림이 보이며, 칩이 존재한다는 것과 모든 프레임을 정확히 계측할 수 있다는 것은 다릅니다.')
p('올바른 보정으로도 기존의 24개 표본 탐색 결과는 0개였습니다. 192개 표본 재탐색에서는 214·218·238·252·347프레임에 원 후보가 품질 기준을 통과했고, 제안 개수가 1개가 되었습니다. 이 결과는 개수 제안이며, 각 후보가 모두 독립 정답 판정된 관측이라는 뜻은 아닙니다. v4는 실패를 즉시 종료하기 전에 이 추가 시간 탐색을 수행합니다.')
p('최종 전체 실행에서는 652프레임 중 관측 50행이 남았고, 그중 35행에는 흐림 경고가 붙었습니다. 물리 속도와 각속도는 각각 5행뿐입니다. 따라서 자동 탐색 실패는 해소했지만, 이 영상으로 자유운동 전체나 물리 계수를 신뢰성 있게 추정할 근거는 부족합니다. 전체 녹화에는 칩이 가려지거나 화면 밖인 구간도 있으므로 50/652를 검출 정답률로 읽으면 안 됩니다.','note')
h('3.3 손·발사기에 고정되던 잘못된 궤적',3)
fig('hand_track_203502_f149.jpg','203502의 149프레임. 같은 렌즈 조건에서 잘못 고정된 궤적과 최종 v4의 실제 칩 재획득을 비교했습니다.')
p('동일한 렌즈 보정을 적용한 v3.5와 초기 v4 검증 빌드 모두 흐린 무표식 원 후보가 chip_1의 최근 위치를 계속 갱신했습니다. 실제 칩에 두 색 표식이 보여도 이전 잘못된 예측과의 거리가 허용 범위를 넘어서 재획득이 차단되었습니다. 149프레임의 잘못된 중심은 (856.7, 893.3) px였고, 최종 v4는 실제 칩 위치인 약 (319.6, 822.4) px로 돌아왔습니다. 좌표는 검출 중심이며 독립 정답 오차 수치가 아닙니다.')
p('흐림 경고만 있고 두 표식이 확인되지 않으면 신뢰 추적 상태를 갱신하지 않게 했습니다. 오래된 추적이 정상적으로 만료되어 실제 표식으로 다시 연결됩니다. 203502의 초기 v4 대비 최종 v4에서 속도 계산 행은 298→511, 흐림 경고 행은 268→6으로 바뀌었습니다. 이는 검증 도중 확인한 중간 빌드와의 비교입니다. 같은 보정 조건의 v3.5는 268개 흐림 경고 관측을 포함한 상태에서 속도를 548행 계산했으므로, 단순히 계산된 숫자가 많다고 더 좋은 결과는 아닙니다.')
h('4. 시뮬레이션이 실제 궤적과 다른 정도')
p('단일 칩 영상 203246에서 손이 떨어진 뒤 구간을 사용해 기존 Farkas 모델의 바닥 마찰계수를 탐색 적합했습니다. 명목 격자·시간·관성 가정 아래 μ=0.3364128이 나왔고, 적합 구간은 200~243프레임 44개 관측입니다. 이 구간의 위치 RMSE는 약 0.384 mm, 회전각 RMSE는 약 1.296°였습니다.')
p('같은 촬영 세션의 다른 영상 203310에는 μ를 그대로 고정했습니다. 186~197프레임의 12개 초기 관측으로 위치·속도·각도·각속도의 초기 상태만 구하고, 그 초기 구간을 점수에서 제외했습니다. 이후 198~374프레임을 예측했습니다. 시험 영상의 마찰계수는 다시 맞추지 않았습니다.')
table(['측정값','다른 영상 203310'],[['평가 시간','0.7342초 / 선언된 물리 시간'],['위치 RMSE','8.156 mm'],['최대 위치 차이','9.700 mm'],['회전각 RMSE','20.786°'],['관찰된 차이','예측 정지 위치가 관측 궤적보다 짧고, 회전량은 더 큼']])
fig('farkas_holdout.png','203246의 마찰계수를 고정해 203310을 예측한 결과. 표시 오차는 영상으로부터 추출한 관측과의 차이이며 독립 측정기의 절대 오차가 아닙니다.')
p('한 영상에 잘 맞는 계수가 다른 영상까지 잘 예측한다는 결론은 성립하지 않았습니다. 마찰/압력 분포/관성 가정의 부적합, 실험 조건 차이, 추적 및 보정 오차가 함께 작용할 수 있습니다. 이 자료만으로 그중 하나를 유일한 원인이라고 특정하지 않았고, 시험 영상에 재적합하여 차이를 숨기지 않았습니다. 모델의 일반화 문제는 남은 한계입니다. 다른 촬영 세션까지의 검증도 수행하지 않았습니다.','note')
if (evidence/'farkas_extra_holdouts.json').exists():
 extra=json.loads((evidence/'farkas_extra_holdouts.json').read_text(encoding='utf-8'))
 table(['추가 시험 영상','평가 시간','위치 RMSE','회전각 RMSE'],[[x['video'],number(x.get('scored_duration_s'),4)+' s',number(x.get('position_rmse_mm'),3)+' mm',number(x.get('angle_rmse_deg'),3)+'°'] for x in extra])
 p('추가 시험도 마찰계수는 다시 맞추지 않았습니다. 203408은 385프레임 이후, 203122는 180프레임 이후의 손에서 분리된 구간을 확인해 사용했습니다. 각 영상에서 품질 기준을 만족하는 연속 구간 길이가 다르므로 짧은 예측의 낮은 오차를 긴 예측과 같은 조건으로 비교하거나 단순 평균하면 안 됩니다. 전체 49개에 대해 물리 모델 계수 적합을 수행한 것은 아닙니다.')
h('5. 보정·시간·물성의 해석')
table(['보정 영상','프레임','렌즈 시점 수','별도 구간 재투영 RMS','사용 대상'],[[r['video'],r['frames'],60,number(r['calibration_holdout_px'],4)+' px','20:01~20:04 실험' if '200058' in r['video'] else '20:31 이후 실험'] for r in cal])
p('두 보정 영상 모두 끝부분 보정판의 안정 상태 검사를 통과했습니다. 다만 사람이 보정판과 실험면의 동일 평면임을 확인했다고 조작하지 않았습니다(floor_confirmed=False). 렌즈 계수만 사용하고 실험 영상의 바닥 격자로 평면 변환을 따로 구했습니다. 보정 잔차는 같은 판/격자의 내부 일관성 검사입니다.')
table(['항목','이번 계산의 가정','정확한 실험값으로 확정하려면'],[['격자','22.5 mm / 23.8889 mm, 기존 설정','실제 바닥 격자 간격의 독립 측정'],['칩','지름 40 mm, 질량 12 g, 균질 원판 관성','칩별 지름·질량·관성/질량 분포 확인'],['시간','재생 PTS ÷ 8. Android 메타데이터에는 촬영 240 fps','외부 시간 기준 또는 실제 캡처 시간 확인'],['각도','표식 관측과 500 rad/s 각속도 상한을 사용한 조건부 unwrap','빠른 회전의 앨리어싱과 가려진 표식 검토'],['면','근사 평면 및 거의 수직인 카메라의 격자 모델','들림·기울어짐·프레임별 카메라 이동 검사']])
h('6. GUI 변경 및 실행 안내')
fig('v4_gui_range.png','실제 영상으로 시작 189, 종료 238프레임을 선택했습니다. 종료가 시작보다 빠른 188프레임은 거부하고 정상 범위는 저장했습니다.')
p('저장소 루트에서 Windows는 SETUP.cmd를 실행한 뒤 RUN.cmd를 실행하세요. Python 3.12와 패키지 설치용 인터넷이 필요합니다. 독립 EXE 패키지는 아닙니다. 새 폴더의 가상환경을 권장합니다. 해당 세션의 보정 영상을 먼저 선택하고, 실험 영상을 폴더로 추가한 다음 실제 칩 개수와 손 접촉이 끝난 시작 프레임을 확인하세요. 종료 프레임으로 재접촉·화면 이탈 구간을 제한할 수 있습니다.')
p('검증 환경은 Linux / CPython 3.12 / PySide6 offscreen입니다. Windows 실행 스크립트는 검토했으나 Windows 실기기에서 실행하지 않았습니다. 고정 의존성은 requirements-v4-tested.txt에 있습니다. 동일 픽셀 회색조 재사용은 측정 해상도를 줄이지 않으며, 시간·메모리 성능의 공정한 벤치마크 수치로는 제시하지 않습니다.')
h('7. 전체 51개 영상별 결과')
p('아래 “완료”는 분석 및 결과 저장 완료를 뜻합니다. 관측률은 전체 녹화에서 등록된 칩×프레임 대비 관측 행 비율로, 가림·화면 이탈·손 접촉을 포함하므로 정답률이 아닙니다. 물리량 행 수가 0이거나 사건이 “unmeasurable”이면 값을 0으로 해석하지 마세요. 파일명에는 날짜 접두사 20260928_가 공통으로 붙습니다.')
labels={'complete':'완료','failed':'분석 실패','publication_failed':'결과 저장 실패','running':'실행 중','not_started':'대기'}
data=[]
for r in ex:
 issues=[]
 if r.get(B+'_count_mismatch'):issues.append('기본 v3.5 개수 불일치')
 if r.get(V+'_count_mismatch'):issues.append('v4 개수 재검토')
 if r.get(V+'_geometry_status')!='provisional':issues.append('v4 기하 확인')
 if r.get(V+'_blur_review_rows'):issues.append('흐림 '+str(r[V+'_blur_review_rows'])+'행')
 if r.get(V+'_event_candidates'):issues.append('사건 '+str(r[V+'_event_candidates'])+'개')
 if r.get(V+'_error'):issues.append(r[V+'_error'])
 data.append([r['video'][9:15],r['frames'],r['visual_chip_count'],f"{r.get(B+'_count','—')} / {labels.get(r.get(B+'_status'),r.get(B+'_status'))}",f"{r.get(V+'_count','—')} / {labels.get(r.get(V+'_status'),r.get(V+'_status'))}"+(' (재시도)' if r['video']=='20260928_200141.mp4' else ''),number((r.get(V+'_observed_fraction_all_target_frames') or 0)*100,1)+'%',f"{r.get(V+'_physical_velocity_rows',0)} / {r.get(V+'_angular_velocity_rows',0)}",'; '.join(issues) or '세부 품질 파일 확인'])
table(['영상 시각','프레임','실제 칩','v3.5 기본 개수 / 상태','v4 개수 / 상태','v4 관측률','속도 / 각속도 행','검토 사항'],data)
p('보정 영상 200058과 203026은 위 5절에 별도로 기록했습니다. 나머지 49개와 합쳐 폴더의 51개 전체입니다. 영상별 자세한 사건 프레임, 연속 검토 구간, 품질 정보, 궤적 및 원본 SHA-256은 archive/releases/v4.0.0의 동결 ZIP에 있습니다.')
h('7.1 특히 유효 운동학 관측이 적은 영상',3)
limited=sorted(ex,key=lambda r:r.get(V+'_physical_velocity_rows') or 0)[:5]
table(['영상','전체 프레임','관측 행','속도 행','각속도 행','흐림 경고 행'],[[r['video'][9:15],r['frames'],r.get(V+'_observation_rows'),r.get(V+'_physical_velocity_rows'),r.get(V+'_angular_velocity_rows'),r.get(V+'_blur_review_rows')] for r in limited])
p('이 영상들은 처리 완료 상태여도 물리 모델 적합에 사용할 연속·선명 표본이 짧습니다. 화면 이탈과 발사 전 가림이 많아 전체 녹화 관측률만으로 검출 성능을 비교하지 않았습니다.')
h('7.2 충돌 후보별 정확한 프레임과 보류 사유',3)
event_rows=[]
kinds={'unmeasurable':'계측 불충분','isolated_binary':'고립 이체 후보','invalid':'기하/상태 불확실','persistent_contact':'근접 지속 후보','near_simultaneous':'근접 동시 후보','simultaneous_multi_contact':'동시 다중 후보','noncontact_pass':'비접촉 통과 후보'}
for r in ex:
 for ev in r.get(V+'_events',[]):event_rows.append([r['video'][9:15],'/'.join(ev.get('pair') or []),str(ev.get('frame_start'))+'~'+str(ev.get('frame_end')),ev.get('closest_frame'),kinds.get(ev.get('kind'),ev.get('kind')),ev.get('reason')])
table(['영상','쌍','후보 구간','최접근','판정','사유'],event_rows)
p('프레임은 0부터 세는 디코딩 인덱스입니다. 근접 지속·동시 후보는 영상에서 실제 접촉 형태를 확정한 라벨이 아닙니다. 전후 관측 또는 사건 검토가 부족하면 계수를 비워 두는 것이 정상이며, 빈 값을 반발계수 0으로 바꾸면 안 됩니다.')
h('8. 재현 자료와 남은 검증')
p('results/v4/summaries/video_summary.csv는 전체 영상 비교표, all_results.json은 상세 요약입니다. 전체 영상별 산출물은 archive/releases/v4.0.0의 동결 ZIP에 보존했고, results/v4/evidence에는 보고서가 직접 사용하는 보정값·모델 검증·GUI 증거만 선별했습니다.')
p('개발 도중 발견한 오류를 추가 수정한 뒤 코드를 고정하고 최종 v4로 실험 49개 전체를 다시 실행했습니다. 본 비교표의 v4 데이터는 이 마지막 배치입니다. 모든 최종 run manifest의 code_hash를 배포 소스와 대조했습니다. 중간 빌드 자료는 원인 비교 증거로만 별도 표시하며, 배포 데이터와 섞지 않았습니다.')
p('남은 검증은 독립 정답 라벨에 의한 중심·각도 오차, 외부 시간·길이 검증, 충돌 전후의 고립 표본과 사건 승인, 다른 촬영 세션의 물리 모델 예측, Windows 실기기 실행입니다. v4는 확인된 코드 오류를 수정하고 오류 원인과 검토 대상을 더 잘 드러내지만, 현재 자료에서 모든 물리 계수가 검증되었다고 주장하지 않습니다.')
css='''*{box-sizing:border-box}body{margin:0;background:#edf1f5;color:#17283b;font:16px/1.75 system-ui,-apple-system,"Noto Sans KR","Malgun Gothic",sans-serif}main{max-width:1180px;margin:32px auto;padding:52px 58px;background:white;box-shadow:0 10px 50px #182a4212;border-top:8px solid #236a87}h1{font-size:34px;line-height:1.35;letter-spacing:-1px;margin:0 0 24px}h2{font-size:25px;margin:54px 0 18px;border-bottom:2px solid #dce5eb;padding-bottom:10px}h3{font-size:20px;margin-top:36px}p{margin:16px 0}.lead{font-size:18px;color:#28475d}.note{background:#fff5df;border-left:4px solid #c68a24;padding:18px 22px}.table-wrap{overflow-x:auto;margin:20px 0}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:12px 14px;border-bottom:1px solid #dfe6ec}th{background:#19394e;color:white;font-weight:600}tr:nth-child(even){background:#f5f8fa}figure{margin:28px 0}img{display:block;max-width:100%;height:auto;margin:auto;border:1px solid #dce5eb}figcaption{font-size:14px;color:#526477;margin:12px 0}footer{margin-top:44px;padding-top:20px;border-top:1px solid #dce5eb;color:#6b7b8c;font-size:13px}@media(max-width:750px){main{margin:0;padding:26px 18px}h1{font-size:28px}th,td{padding:9px}table{font-size:12px}}@media print{body{background:white}main{box-shadow:none;margin:0;padding:12px;border:0}h2{break-after:avoid}tr,img{break-inside:avoid}}'''
page='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PokerChip Astra v4 실제 영상 검증 보고서</title><style>'+css+'</style></head><body><main>'+''.join(parts)+'<footer>첨부 원본 및 지정 Drive 영상으로 수행한 개발 검증 · 독립 절대 정확도 인증 아님</footer></main></body></html>'
(out/'VALIDATION_REPORT_KO.html').write_text(page,encoding='utf-8');(out/'VALIDATION_REPORT_KO.md').write_text('\n'.join(md),encoding='utf-8');print('report written',len(page))
