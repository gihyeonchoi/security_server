import requests
import json

# view_tag 에 데이터 전송 -> RFID 등록
url = 'http://localhost:8000/RFID/test/'
data = {
    'rfid_code': 'AB12CD34',
    }

# 실제 작동 테스트
# url = 'http://localhost:8000/RFID/card_use/'
# data = {
#     'rfid_code': 'AB12CD34',
#     'device_code' : 'Q1W2E3R4'
#     }  # 테스트용 RFID 코드

response = requests.post(url, json=data)
print(response.json())