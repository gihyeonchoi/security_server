# CCTV/roboflow_service.py - InferencePipeline 사용 버전
import asyncio
import base64
import json
import time
import cv2
import numpy as np
from typing import Dict, Any, List
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from .models import CameraConfig

try:
    from inference import InferencePipeline
except ImportError:
    print("Warning: inference package not installed. Install with: pip install inference")
    InferencePipeline = None

class AsyncInferencePipelineManager:
    """InferencePipeline을 사용한 비동기 카메라 스트림 관리자"""
    
    def __init__(self):
        self.pipelines: Dict[int, InferencePipeline] = {}
        self.active_connections: Dict[int, List] = {}  # 카메라별 WebSocket 연결 관리
        self.channel_layer = get_channel_layer()
        
    async def start_camera_pipeline(self, camera_id: int):
        """특정 카메라의 InferencePipeline 시작"""
        if camera_id in self.pipelines:
            print(f"카메라 {camera_id} 이미 실행 중")
            return
            
        try:
            camera = await self._get_camera_config(camera_id)
            if not camera:
                print(f"카메라 {camera_id} 설정을 찾을 수 없음")
                return
                
            print(f"카메라 {camera_id} 설정:")
            # print(f"  - API Key: {camera.api_key[:10]}...")
            print(f"  - API Key: {camera.api_key}")
            print(f"  - Workspace: {camera.workspace_name}")
            print(f"  - Workflow: {camera.workflow_id}")
            print(f"  - RTSP URL: {camera.rtsp_url}")
            print(f"  - Max FPS: {camera.max_fps}")
                
            # 비동기 sink wrapper 생성 (스레드 안전)
            def async_sink_wrapper(result, video_frame):
                print(f"📡 카메라 {camera_id} 감지 결과 수신")
                try:
                    # 메인 스레드의 이벤트 루프에서 실행
                    import threading
                    def run_in_main_thread():
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # 이미 실행 중인 루프에 추가
                                asyncio.run_coroutine_threadsafe(
                                    self._handle_detection_result(camera_id, result, video_frame), 
                                    loop
                                )
                            else:
                                # 새 루프 생성
                                loop.run_until_complete(
                                    self._handle_detection_result(camera_id, result, video_frame)
                                )
                        except RuntimeError:
                            # 동기적으로 처리
                            self._handle_detection_result_sync(camera_id, result, video_frame)
                    
                    # 별도 스레드에서 실행
                    thread = threading.Thread(target=run_in_main_thread)
                    thread.daemon = True
                    thread.start()
                    
                except Exception as e:
                    print(f"❌ Sink wrapper 오류: {e}")
                    # 동기적으로 처리
                    self._handle_detection_result_sync(camera_id, result, video_frame)
            
            if InferencePipeline is None:
                print(f"❌ InferencePipeline이 설치되지 않음")
                return
            
            print(f"🚀 카메라 {camera_id} InferencePipeline 초기화 중...")
            
            # InferencePipeline 초기화 (실제 RTSP 스트림 사용)
            print(f"🔍 RTSP URL: {camera.rtsp_url}")
            
            pipeline = InferencePipeline.init_with_workflow(
                api_key=camera.api_key,
                workspace_name=camera.workspace_name,
                workflow_id=camera.workflow_id,
                video_reference=camera.rtsp_url,
                max_fps=camera.max_fps,
                on_prediction=async_sink_wrapper,
            )
            
            print(f"🔄 카메라 {camera_id} Pipeline 시작 중...")
            
            # Pipeline 시작 (비동기 처리)
            def start_pipeline():
                try:
                    print(f"📹 카메라 {camera_id} Pipeline 실제 시작...")
                    pipeline.start()
                    print(f"✅ 카메라 {camera_id} Pipeline 시작 완료")
                except Exception as e:
                    print(f"❌ Pipeline 시작 중 오류: {e}")
                    import traceback
                    traceback.print_exc()
            
            # 별도 스레드에서 Pipeline 시작
            import threading
            pipeline_thread = threading.Thread(target=start_pipeline)
            pipeline_thread.daemon = True
            pipeline_thread.start()
            
            self.pipelines[camera_id] = pipeline
            print(f"🚀 카메라 {camera_id} Pipeline 스레드 시작됨")
            
        except Exception as e:
            print(f"❌ 카메라 {camera_id} Pipeline 시작 실패: {e}")
            import traceback
            traceback.print_exc()
    
    async def stop_camera_pipeline(self, camera_id: int):
        """특정 카메라의 InferencePipeline 중지"""
        if camera_id not in self.pipelines:
            print(f"카메라 {camera_id} Pipeline이 실행 중이 아님")
            return
            
        try:
            pipeline = self.pipelines[camera_id]
            
            # Pipeline 중지 (별도 스레드에서)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, pipeline.terminate)
            
            del self.pipelines[camera_id]
            print(f"🛑 카메라 {camera_id} Pipeline 중지")
            
        except Exception as e:
            print(f"❌ 카메라 {camera_id} Pipeline 중지 실패: {e}")
    
    async def start_all_active_cameras(self):
        """모든 활성 카메라의 Pipeline 시작"""
        active_cameras = await self._get_active_cameras()
        
        tasks = []
        for camera in active_cameras:
            task = asyncio.create_task(self.start_camera_pipeline(camera.id))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            print(f"✅ {len(tasks)}개 카메라 Pipeline 시작 완료")
    
    async def stop_all_cameras(self):
        """모든 카메라의 Pipeline 중지"""
        camera_ids = list(self.pipelines.keys())
        
        tasks = []
        for camera_id in camera_ids:
            task = asyncio.create_task(self.stop_camera_pipeline(camera_id))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            print(f"🛑 {len(tasks)}개 카메라 Pipeline 중지 완료")
    
    async def _handle_detection_result(self, camera_id: int, result: Dict[Any, Any], video_frame):
        """감지 결과 처리 및 WebSocket 브로드캐스트"""
        try:
            # 감지 결과 파싱
            detections = self._parse_detection_result(result)
            
            # 프레임을 base64로 인코딩 (선택사항)
            frame_data = None
            if video_frame is not None:
                frame_data = self._encode_frame_to_base64(video_frame)
            
            # WebSocket으로 브로드캐스트
            await self._broadcast_to_websocket(camera_id, {
                'camera_id': camera_id,
                'timestamp': time.time(),
                'detections': detections,
                'frame_data': frame_data,
                'detection_count': len(detections)
            })
            
            print(f"📡 카메라 {camera_id}: {len(detections)}개 객체 감지")
            
        except Exception as e:
            print(f"❌ 감지 결과 처리 오류 (카메라 {camera_id}): {e}")
    
    def _handle_detection_result_sync(self, camera_id: int, result: Dict[Any, Any], video_frame):
        """감지 결과 동기적 처리 (fallback)"""
        try:
            # 감지 결과 파싱
            detections = self._parse_detection_result(result)
            
            # 프레임을 base64로 인코딩 (필수)
            frame_data = None
            if video_frame is not None:
                frame_data = self._encode_frame_to_base64(video_frame)
                if frame_data:
                    print(f"✅ 카메라 {camera_id} 프레임 인코딩 성공")
                else:
                    print(f"❌ 카메라 {camera_id} 프레임 인코딩 실패")
            
            # Django Channels 동기적 브로드캐스트
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            
            channel_layer = get_channel_layer()
            if channel_layer:
                data = {
                    'camera_id': camera_id,
                    'timestamp': time.time(),
                    'detections': detections,
                    'frame_data': frame_data,
                    'detection_count': len(detections)
                }
                
                print(f"📤 카메라 {camera_id} WebSocket 브로드캐스트 시도...")
                
                try:
                    # 개별 카메라 그룹에 브로드캐스트
                    async_to_sync(channel_layer.group_send)(
                        f"camera_{camera_id}",
                        {
                            "type": "detection_update",
                            "data": data
                        }
                    )
                    print(f"✅ 카메라 {camera_id} 개별 그룹 브로드캐스트 성공")
                except Exception as e:
                    print(f"❌ 카메라 {camera_id} 개별 그룹 브로드캐스트 실패: {e}")
                
                try:
                    # 라이브 뷰 그룹에 브로드캐스트
                    async_to_sync(channel_layer.group_send)(
                        "live_view",
                        {
                            "type": "detection_update",
                            "data": data
                        }
                    )
                    print(f"✅ 카메라 {camera_id} 라이브 뷰 그룹 브로드캐스트 성공")
                except Exception as e:
                    print(f"❌ 카메라 {camera_id} 라이브 뷰 그룹 브로드캐스트 실패: {e}")
            else:
                print(f"❌ Channel layer가 없음")
            
            print(f"📡 카메라 {camera_id}: {len(detections)}개 객체 감지 (동기)")
            
        except Exception as e:
            print(f"❌ 동기 감지 결과 처리 오류 (카메라 {camera_id}): {e}")
            import traceback
            traceback.print_exc()
    
    def _parse_detection_result(self, result: Dict[Any, Any]) -> List[Dict]:
        """Roboflow 감지 결과 파싱"""
        detections = []
        
        try:
            # InferencePipeline 결과 구조에 맞게 파싱
            if 'predictions' in result:
                predictions = result['predictions']
            elif isinstance(result, list):
                predictions = result
            else:
                predictions = [result]
            
            for prediction in predictions:
                if isinstance(prediction, dict):
                    detection = {
                        'class': prediction.get('class', 'unknown'),
                        'confidence': prediction.get('confidence', 0.0),
                        'x': prediction.get('x', 0),
                        'y': prediction.get('y', 0),
                        'width': prediction.get('width', 0),
                        'height': prediction.get('height', 0)
                    }
                    detections.append(detection)
                    
        except Exception as e:
            print(f"감지 결과 파싱 오류: {e}")
            
        return detections
    
    def _encode_frame_to_base64(self, frame) -> str:
        """프레임을 base64로 인코딩"""
        try:
            img_array = None
            
            if hasattr(frame, 'numpy_image'):
                # InferencePipeline의 VideoFrame 객체인 경우
                img_array = frame.numpy_image
                print(f"VideoFrame 크기: {img_array.shape}")
            elif hasattr(frame, 'image'):
                # 다른 형태의 프레임 객체
                img_array = frame.image
                print(f"Frame image 크기: {img_array.shape}")
            elif isinstance(frame, np.ndarray):
                # numpy array인 경우
                img_array = frame
                print(f"NumPy array 크기: {img_array.shape}")
            else:
                print(f"알 수 없는 프레임 타입: {type(frame)}")
                return None
                
            if img_array is None:
                print("프레임 데이터를 추출할 수 없음")
                return None
            
            # 이미지 형태 확인 및 변환
            if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                # RGB를 BGR로 변환 (OpenCV 사용)
                if img_array.dtype != np.uint8:
                    img_array = (img_array * 255).astype(np.uint8)
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # JPEG로 인코딩
            success, buffer = cv2.imencode('.jpg', img_array, [cv2.IMWRITE_JPEG_QUALITY, 85])
            
            if not success:
                print("JPEG 인코딩 실패")
                return None
            
            # base64 인코딩
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            return f"data:image/jpeg;base64,{img_base64}"
            
        except Exception as e:
            print(f"프레임 인코딩 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _broadcast_to_websocket(self, camera_id: int, data: Dict):
        """WebSocket으로 데이터 브로드캐스트"""
        try:
            if self.channel_layer:
                # 개별 카메라 그룹에 브로드캐스트
                await self.channel_layer.group_send(
                    f"camera_{camera_id}",
                    {
                        "type": "detection_update",
                        "data": data
                    }
                )
                
                # 라이브 뷰 그룹에도 브로드캐스트
                await self.channel_layer.group_send(
                    "live_view",
                    {
                        "type": "detection_update",
                        "data": data
                    }
                )
                
        except Exception as e:
            print(f"WebSocket 브로드캐스트 오류: {e}")
    
    async def _get_camera_config(self, camera_id: int):
        """데이터베이스에서 카메라 설정 조회 (비동기)"""
        from channels.db import database_sync_to_async
        
        @database_sync_to_async
        def get_camera():
            try:
                return CameraConfig.objects.get(id=camera_id, is_active=True)
            except CameraConfig.DoesNotExist:
                return None
        
        return await get_camera()
    
    async def _get_active_cameras(self):
        """활성 카메라 목록 조회 (비동기)"""
        from channels.db import database_sync_to_async
        
        @database_sync_to_async
        def get_cameras():
            return list(CameraConfig.objects.filter(is_active=True))
        
        return await get_cameras()
    
    def get_pipeline_status(self) -> Dict[int, str]:
        """현재 실행 중인 Pipeline 상태 반환"""
        return {
            camera_id: "running" 
            for camera_id in self.pipelines.keys()
        }
    


# 전역 매니저 인스턴스
pipeline_manager = AsyncInferencePipelineManager()


# 편의 함수들
async def start_camera_detection(camera_id: int):
    """카메라 감지 시작"""
    await pipeline_manager.start_camera_pipeline(camera_id)

async def stop_camera_detection(camera_id: int):
    """카메라 감지 중지"""
    await pipeline_manager.stop_camera_pipeline(camera_id)

async def start_all_detection():
    """모든 활성 카메라 감지 시작"""
    await pipeline_manager.start_all_active_cameras()

async def stop_all_detection():
    """모든 카메라 감지 중지"""
    await pipeline_manager.stop_all_cameras()

def get_detection_status() -> Dict[int, str]:
    """현재 감지 상태 조회"""
    return pipeline_manager.get_pipeline_status()


# 사용 예시:
# import asyncio
# from CCTV.roboflow_service import pipeline_manager
# 
# async def main():
#     # 모든 활성 카메라 시작
#     await pipeline_manager.start_all_active_cameras()
#     
#     # 특정 카메라만 시작
#     await pipeline_manager.start_camera_pipeline(1)
#     
#     # 10초 대기
#     await asyncio.sleep(10)
#     
#     # 모든 카메라 중지
#     await pipeline_manager.stop_all_cameras()
# 
# # 실행
# asyncio.run(main())