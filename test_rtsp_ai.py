import cv2
import requests
import base64
import json
import time
import threading

class SimpleRoboflowDetector:
    def __init__(self, rtsp_url, api_key, model_id):
        self.rtsp_url = rtsp_url
        self.api_key = api_key
        self.model_id = model_id
        # Hosted API URL (로컬 서버 불필요!)
        self.api_url = f"https://detect.roboflow.com/{model_id}"
        
    def connect_camera(self):
        """RTSP 카메라 연결"""
        print(f"카메라 연결 중: {self.rtsp_url}")
        self.cap = cv2.VideoCapture(self.rtsp_url)
        
        if not self.cap.isOpened():
            raise Exception("카메라 연결 실패")
        
        print("카메라 연결 성공!")
        
    def detect_objects(self, frame):
        """Roboflow Hosted API로 객체 탐지 (서버 설치 불필요)"""
        try:
            # 이미지 크기 조정
            height, width = frame.shape[:2]
            if width > 640:
                scale = 640 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))
            
            # JPEG 인코딩 및 base64 변환
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # API 요청 (가장 간단한 방법)
            response = requests.post(
                self.api_url,
                params={
                    "api_key": self.api_key,
                    "confidence": 40,  # 신뢰도 40%
                    "overlap": 30      # NMS 30%
                },
                data=img_base64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=5
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('predictions', [])
            else:
                print(f"API 오류: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"탐지 오류: {e}")
            return []
    
    def draw_detections(self, frame, predictions):
        """탐지 결과 그리기"""
        for pred in predictions:
            # 바운딩 박스 좌표
            x = int(pred['x'] - pred['width'] / 2)
            y = int(pred['y'] - pred['height'] / 2)
            w = int(pred['width'])
            h = int(pred['height'])
            
            # 클래스와 신뢰도
            class_name = pred['class']
            confidence = pred['confidence']
            
            # 색상 선택
            if class_name == 'person':
                color = (0, 255, 0)  # 녹색
            else:
                color = (255, 0, 0)  # 빨간색
            
            # 바운딩 박스 그리기
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            
            # 라벨 그리기
            label = f"{class_name}: {confidence:.2f}"
            cv2.putText(frame, label, (x, y - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return frame
    
    def run(self):
        """메인 실행"""
        self.connect_camera()
        
        print("실시간 탐지 시작! (q: 종료)")
        last_detection_time = 0
        detection_interval = 2.0  # 2초마다 탐지 (API 부하 방지)
        latest_predictions = []
        
        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("프레임 읽기 실패")
                break
            
            current_time = time.time()
            
            # 2초마다 API 호출
            if current_time - last_detection_time >= detection_interval:
                print("객체 탐지 중...")
                latest_predictions = self.detect_objects(frame)
                print(f"탐지된 객체: {len(latest_predictions)}개")
                last_detection_time = current_time
            
            # 탐지 결과 그리기
            if latest_predictions:
                frame = self.draw_detections(frame, latest_predictions)
            
            # 상태 표시
            status = f"Objects: {len(latest_predictions)} | Next detection in: {detection_interval - (current_time - last_detection_time):.1f}s"
            cv2.putText(frame, status, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # 화면 표시
            cv2.imshow('Roboflow Detection', frame)
            
            # 'q' 키로 종료
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        # 정리
        self.cap.release()
        cv2.destroyAllWindows()

def test_api_connection(api_key, model_id):
    """API 연결 테스트"""
    print("🔍 Roboflow API 연결 테스트 중...")
    
    # 테스트 이미지 생성
    import numpy as np
    test_img = np.zeros((300, 400, 3), dtype=np.uint8)
    cv2.putText(test_img, "TEST", (150, 150), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
    
    # base64 인코딩
    _, buffer = cv2.imencode('.jpg', test_img)
    img_base64 = base64.b64encode(buffer).decode('utf-8')
    
    try:
        response = requests.post(
            f"https://detect.roboflow.com/{model_id}",
            params={"api_key": api_key, "confidence": 40, "overlap": 30},
            data=img_base64,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ API 연결 성공!")
            result = response.json()
            print(f"응답 구조: {list(result.keys())}")
            return True
        else:
            print(f"❌ API 연결 실패: {response.status_code}")
            print(f"오류 내용: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 연결 테스트 실패: {e}")
        return False

def main():
    # ===== 여기만 수정하세요 =====
    RTSP_URL = "rtsp://admin:password123@192.168.5.135:554/stream1"
    API_KEY = "kgm9FxHeHlESLpZy1gn7"
    MODEL_ID = "cctv-naxyo-rur2l/1"  # 또는 다른 모델 ID
    # ========================
    
    print("🚀 Roboflow 간단 탐지 시스템")
    print("📌 로컬 서버 설치 불필요!")
    print("📌 인터넷만 연결되면 OK!")
    print()
    
    # API 연결 테스트
    if not test_api_connection(API_KEY, MODEL_ID):
        print("API 테스트 실패. 설정을 확인하세요.")
        return
    
    # 탐지 시작
    detector = SimpleRoboflowDetector(RTSP_URL, API_KEY, MODEL_ID)
    detector.run()

if __name__ == "__main__":
    main()