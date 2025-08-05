# CCTV/utils.py
from .models import CameraConfig
import requests

class CameraConfigManager:
    """카메라 설정을 가져오고 관리하는 유틸리티 클래스"""
    
    @staticmethod
    def get_camera_config(camera_name):
        """카메라 이름으로 설정 가져오기"""
        try:
            camera = CameraConfig.objects.get(name=camera_name, is_active=True)
            return {
                "api_key": camera.api_key,
                "workspace_name": camera.workspace_name,
                "workflow_id": camera.workflow_id,
                "rtsp_url": camera.rtsp_url,
                "max_fps": camera.max_fps,
            }
        except CameraConfig.DoesNotExist:
            return None
    
    @staticmethod
    def get_all_active_configs():
        """모든 활성 카메라 설정 가져오기"""
        cameras = CameraConfig.objects.filter(is_active=True)
        return {
            camera.name: {
                "api_key": camera.api_key,
                "workspace_name": camera.workspace_name,
                "workflow_id": camera.workflow_id,
                "rtsp_url": camera.rtsp_url,
                "max_fps": camera.max_fps,
            }
            for camera in cameras
        }
    
    @staticmethod
    def get_config_via_api(base_url, camera_id):
        """API를 통해 카메라 설정 가져오기 (외부 시스템 연동용)"""
        try:
            response = requests.get(f"{base_url}/cctv/api/cameras/{camera_id}/config_dict/")
            if response.status_code == 200:
                return response.json()
        except requests.RequestException as e:
            print(f"API 요청 실패: {e}")
        return None

# 사용 예시:
# from CCTV.utils import CameraConfigManager
# 
# # 특정 카메라 설정 가져오기
# config = CameraConfigManager.get_camera_config("CAMERA_1")
# 
# # 모든 활성 카메라 설정 가져오기
# all_configs = CameraConfigManager.get_all_active_configs()
# 
# # API로 가져오기
# config = CameraConfigManager.get_config_via_api("http://localhost:8000", 1)