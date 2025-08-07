from django.apps import AppConfig
import threading
import time


class CctvConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'CCTV'
    verbose_name = 'CCTV 관리 시스템'
    
    def ready(self):
        """Django 서버 시작 시 백그라운드 카메라 스트리밍 및 AI 탐지 시작"""
        # runserver에서 reload 시 중복 실행 방지
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return
            
        # 잠시 대기 후 시작 (Django가 완전히 로드된 후)
        def delayed_startup():
            time.sleep(3)
            self._start_background_services()
        
        startup_thread = threading.Thread(target=delayed_startup, daemon=True)
        startup_thread.start()
        print("🚀 CCTV 백그라운드 서비스가 3초 후 시작됩니다...")
    
    def _start_background_services(self):
        """백그라운드 카메라 스트리밍 및 AI 탐지 시작"""
        try:
            # Django ORM이 준비될 때까지 추가 대기
            import django
            from django.db import connection
            
            # DB 연결 확인
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            
            from .utils import camera_streamer, ai_detection_system
            from .models import Camera
            
            print("\n🔧 CCTV 백그라운드 서비스 시작...")
            
            # 모든 카메라에 대해 백그라운드 스트리밍 시작
            cameras = Camera.objects.all()
            print(f"📹 총 {len(cameras)}개 카메라 발견")
            
            success_count = 0
            for camera in cameras:
                try:
                    # 백그라운드 모드로 카메라 스트리밍 시작
                    if camera_streamer.start_background_streaming(camera.rtsp_url):
                        success_count += 1
                        print(f"✅ 카메라 '{camera.name}' 백그라운드 스트리밍 시작")
                    else:
                        print(f"❌ 카메라 '{camera.name}' 스트리밍 연결 실패")
                except Exception as e:
                    print(f"❌ 카메라 '{camera.name}' 스트리밍 시작 실패: {e}")
            
            print(f"📊 백그라운드 스트리밍: {success_count}/{len(cameras)} 카메라 성공")
            
            # AI 탐지 시스템 자동 시작 (스트리밍이 최소 1개 이상 성공한 경우만)
            if success_count > 0:
                try:
                    ai_detection_system.start_all_detections()
                    print("🤖 AI 탐지 시스템 자동 시작 완료")
                except Exception as e:
                    print(f"❌ AI 탐지 시스템 시작 실패: {e}")
            else:
                print("⚠️ 연결된 카메라가 없어 AI 탐지 시스템을 시작하지 않습니다")
                
            print("🎯 CCTV 백그라운드 서비스 초기화 완료!\n")
            
        except Exception as e:
            print(f"❌ 백그라운드 서비스 시작 중 오류: {e}")
            import traceback
            traceback.print_exc()