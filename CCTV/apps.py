# CCTV/apps.py
from django.apps import AppConfig
import threading
import time

class CctvConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'CCTV'
    
    def ready(self):
        """Django 앱 시작 시 백그라운드 스트리밍 및 AI 탐지 시작"""
        # 마이그레이션 실행 중이면 건너뛰기
        import sys
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return
        
        # runserver 명령어 실행 시에만 동작
        if 'runserver' not in sys.argv:
            return
        
        # 메인 프로세스에서만 실행 (재로드 방지)
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return
        
        print("\n" + "="*60)
        print("🚀 CCTV 시스템 초기화 시작...")
        print("="*60)
        
        def initialize_cctv_system():
            """백그라운드에서 CCTV 시스템 초기화 - 실시간 DB 반영"""
            try:
                # Django가 완전히 로드될 때까지 대기
                time.sleep(2)
                
                from .utils import camera_streamer, ai_detection_system
                from .models import Camera
                
                # 1. 카메라 실시간 모니터링 스레드 시작
                def monitor_cameras():
                    """DB 변경사항을 주기적으로 체크하고 반영"""
                    last_camera_state = {}
                    
                    while True:
                        try:
                            # 현재 DB의 카메라 상태 가져오기
                            current_cameras = Camera.objects.prefetch_related('target_labels').all()
                            current_state = {}
                            
                            for camera in current_cameras:
                                current_state[camera.id] = {
                                    'rtsp_url': camera.rtsp_url,
                                    'name': camera.name,
                                    'location': camera.location,
                                    'has_labels': camera.target_labels.exists(),
                                    'label_count': camera.target_labels.count()
                                }
                            
                            # 변경사항 감지
                            if current_state != last_camera_state:
                                print(f"\n🔄 카메라 설정 변경 감지!")
                                
                                # 추가된 카메라
                                added = set(current_state.keys()) - set(last_camera_state.keys())
                                for camera_id in added:
                                    camera = Camera.objects.get(id=camera_id)
                                    print(f"  ➕ 새 카메라: {camera.name}")
                                    
                                    # 백그라운드 스트리밍 시작
                                    camera_streamer.start_background_streaming(camera.rtsp_url)
                                    
                                    # 타겟 라벨이 있으면 AI 탐지 시작
                                    if current_state[camera_id]['has_labels']:
                                        ai_detection_system.start_detection_for_camera(camera)
                                
                                # 삭제된 카메라
                                removed = set(last_camera_state.keys()) - set(current_state.keys())
                                for camera_id in removed:
                                    print(f"  ➖ 삭제된 카메라: ID {camera_id}")
                                    
                                    # 스트리밍 중지
                                    if camera_id in last_camera_state:
                                        rtsp_url = last_camera_state[camera_id]['rtsp_url']
                                        camera_streamer.stop_background_streaming(rtsp_url)
                                        camera_streamer.cleanup_camera(rtsp_url)
                                    
                                    # AI 탐지 중지
                                    ai_detection_system.stop_detection_for_camera(camera_id)
                                
                                # 수정된 카메라
                                for camera_id in set(current_state.keys()) & set(last_camera_state.keys()):
                                    old = last_camera_state[camera_id]
                                    new = current_state[camera_id]
                                    
                                    # RTSP URL 변경
                                    if old['rtsp_url'] != new['rtsp_url']:
                                        print(f"  🔄 RTSP 변경: {new['name']}")
                                        camera_streamer.stop_background_streaming(old['rtsp_url'])
                                        camera_streamer.cleanup_camera(old['rtsp_url'])
                                        camera_streamer.start_background_streaming(new['rtsp_url'])
                                    
                                    # 타겟 라벨 변경
                                    if old['has_labels'] != new['has_labels'] or old['label_count'] != new['label_count']:
                                        camera = Camera.objects.get(id=camera_id)
                                        print(f"  🎯 타겟 라벨 변경: {new['name']} (라벨 {new['label_count']}개)")
                                        
                                        if new['has_labels']:
                                            # AI 탐지 재시작
                                            ai_detection_system.stop_detection_for_camera(camera_id)
                                            time.sleep(0.5)
                                            ai_detection_system.start_detection_for_camera(camera)
                                        else:
                                            # AI 탐지 중지
                                            ai_detection_system.stop_detection_for_camera(camera_id)
                                
                                last_camera_state = current_state
                                print("  ✅ 변경사항 적용 완료\n")
                            
                            # 10초마다 체크
                            time.sleep(10)
                            
                        except Exception as e:
                            print(f"❌ 카메라 모니터링 오류: {e}")
                            time.sleep(10)
                
                # 모니터링 스레드 시작
                monitor_thread = threading.Thread(
                    target=monitor_cameras,
                    daemon=True,
                    name="CameraMonitor"
                )
                monitor_thread.start()
                print("✅ 카메라 실시간 모니터링 시작")
                
                # 2. 초기 카메라 로드 및 시작
                cameras = Camera.objects.prefetch_related('target_labels').all()
                print(f"\n📹 총 {cameras.count()}개 카메라 발견")
                
                # 백그라운드 스트리밍 시작
                for camera in cameras:
                    try:
                        camera_streamer.start_background_streaming(camera.rtsp_url)
                        print(f"  ✅ '{camera.name}' 백그라운드 스트리밍 시작")
                    except Exception as e:
                        print(f"  ❌ '{camera.name}' 스트리밍 실패: {e}")
                
                # AI 탐지 시작 (타겟 라벨이 있는 카메라만)
                for camera in cameras:
                    if camera.target_labels.exists():
                        try:
                            ai_detection_system.start_detection_for_camera(camera)
                            print(f"  🤖 '{camera.name}' AI 탐지 시작 (라벨 {camera.target_labels.count()}개)")
                        except Exception as e:
                            print(f"  ❌ '{camera.name}' AI 탐지 실패: {e}")
                
                print("\n" + "="*60)
                print("✅ CCTV 시스템 초기화 완료!")
                print("="*60 + "\n")
                
            except Exception as e:
                print(f"❌ CCTV 시스템 초기화 실패: {e}")
                import traceback
                traceback.print_exc()
        
        # 백그라운드 스레드에서 초기화
        init_thread = threading.Thread(
            target=initialize_cctv_system,
            daemon=True,
            name="CCTVInitializer"
        )
        init_thread.start()
        
        # 종료 시 정리 작업 등록
        import atexit
        
        def cleanup():
            try:
                from .utils import camera_streamer, ai_detection_system
                print("\n🧹 CCTV 시스템 종료 중...")
                
                # 모든 스트리밍 중지
                camera_streamer.stop_all_background_streaming()
                
                # 모든 AI 탐지 중지
                ai_detection_system.stop_all_detections()
                
                # 리소스 정리
                camera_streamer.cleanup_all_resources()
                
                print("✅ CCTV 시스템 정리 완료")
            except Exception as e:
                print(f"⚠️ 정리 중 오류: {e}")
        
        atexit.register(cleanup)