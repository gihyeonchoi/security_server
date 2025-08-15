import requests
import json
import time
import random

# 서버 주소
url = "http://127.0.0.1:8000/map/location/"

# 좌표 범위 설정
LAT_MIN = 37.798934
LAT_MAX = 37.79939
LON_MIN = 127.777857
LON_MAX = 127.779301

# 반복 요청
while True:
    # 랜덤 좌표 생성
    latitude = round(random.uniform(LAT_MIN, LAT_MAX), 6)
    longitude = round(random.uniform(LON_MIN, LON_MAX), 6)

    # 보낼 데이터 구성
    data = {
        "device_id": "device123",
        "latitude": latitude,
        "longitude": longitude,
        "altitude": 101.3532,         # 고도는 고정
        "location_id": 3
    }

    try:
        response = requests.post(
            url,
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )
        print("응답 코드:", response.status_code)
        print("보낸 좌표: lat =", latitude, ", lon =", longitude)
        print("응답 내용:", response.json())
    except Exception as e:
        print("요청 중 오류 발생:", e)

    # 1초 대기
    time.sleep(1)
