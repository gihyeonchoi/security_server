import requests
import json

url = 'http://localhost:8000/RFID/test/'
data = {'rfid_code': 'AB12CD34'}  # 테스트용 RFID 코드

response = requests.post(url, json=data)
print(response.json())