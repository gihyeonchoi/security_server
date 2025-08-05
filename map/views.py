# map/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt # csrf 보호 비활성화를 위해 import
from CCTV.models import Camera # CCTV 앱의 Camera 모델을 가져옵니다.
import json

# Flask의 전역 변수처럼, 서버가 실행되는 동안 위치를 메모리에 저장합니다.
# (주의: 서버가 재시작되면 정보는 초기화됩니다.)
latest_location = {
    "latitude": None,
    "longitude": None,
    "altitude": None
}

def map_view(request):
    return render(request, 'map/map.html')

# 외부 장치에서 CSRF 토큰 없이 POST 요청을 보내므로, 이 View에 대해서만 CSRF 보호를 비활성화합니다.
@csrf_exempt
def location_api(request):
    global latest_location

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            latitude = data.get('latitude')
            longitude = data.get('longitude')
            altitude = data.get('altitude')

            if latitude is not None and longitude is not None and altitude is not None:
                latest_location = {
                    "latitude": latitude,
                    "longitude": longitude,
                    "altitude": altitude
                }
                print(f"📡 POST 수신: {latest_location}")
                return JsonResponse({"status": "ok", "message": "Location received"})
            else:
                return JsonResponse({"status": "error", "message": "Missing location data"}, status=400)
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)
    
    elif request.method == 'GET':
        # print(f"🛰️ GET 요청: 저장된 위치 전송 - {latest_location}")
        return JsonResponse(latest_location)
    
def map_view(request):
    # DB에서 특정 카메라 정보를 가져옵니다.
    try:
        # 이름이 'camera1'인 객체를 찾습니다.
        camera_floor1 = Camera.objects.get(name='테스트카메라1') 
    except Camera.DoesNotExist:
        # 만약 'camera1'이라는 이름의 데이터가 없으면 None을 할당합니다.
        camera_floor1 = None

    # 나중에 2층 카메라도 추가할 것을 대비해 미리 작성합니다.
    try:
        camera_floor2 = Camera.objects.get(name='camera2')
    except Camera.DoesNotExist:
        camera_floor2 = None

    # 템플릿에 전달할 데이터 'context'를 만듭니다.
    context = {
        'camera1': camera_floor1,
        'camera2': camera_floor2,
    }
    
    # context를 템플릿으로 전달하며 페이지를 렌더링합니다.
    return render(request, 'map/map.html', context)