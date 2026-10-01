# 의존성과 배포 구성

이 ZIP은 요청에 따라 작성한 수정 가능한 프로젝트 소스와 자체 합성 fixture·검사·문서를 포함합니다. 사용자 제공 논문 PDF, 과거 영상, 칩 사진, 가상환경 또는 설치된 third-party wheel은 포함하지 않습니다. 사용자의 원본 자료에 대한 권리를 이 프로젝트가 변경하거나 부여하지 않습니다.

프로젝트 소스는 사용자가 실행·검토·수정할 수 있도록 제공했습니다. 별도 공개배포 라이선스는 사용자가 정할 수 있습니다. 타사 라이브러리의 라이선스와 재배포 조건은 별개입니다. EXE나 전체 Python 환경을 묶어 배포한 제품이 아닙니다.

설치 버전은 `requirements-lock.txt`로 고정했습니다. 설치 후 각 패키지의 dist-info/METADATA 및 licenses 폴더에서 실제 라이선스 전문과 notices를 확인할 수 있습니다. 특히 PySide6/Qt, OpenCV 및 PyAV에 포함된 native 구성요소는 프로젝트 Python 소스와 같은 라이선스로 간주하지 마세요. 코덱 가용성은 설치된 PyAV/FFmpeg build에 따라 달라집니다.

주요 용도: NumPy/SciPy 수치계산, opencv-contrib-python 경계·표식·ChArUco, PyAV 영상/PTS, PySide6 GUI, Matplotlib 그래프, openpyxl 요약 XLSX, psutil 자원 측정, pytest 테스트입니다. PyMuPDF/Poppler는 전달 논문 검토에만 사용했으며 프로그램 의존성에서는 제외했습니다.

`validation/dependency_metadata.json`은 검증 환경에서 읽은 패키지명·버전·라이선스 메타데이터입니다. 이 파일은 타사 라이선스 전문을 대신하지 않습니다.
