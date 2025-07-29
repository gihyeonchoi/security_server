import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import CameraConfig

class CameraDetectionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        self.room_group_name = f'camera_{self.camera_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        
        if message_type == 'start_detection':
            # 감지 시작 신호
            await self.send(text_data=json.dumps({
                'type': 'detection_status',
                'status': 'started',
                'camera_id': self.camera_id
            }))
        elif message_type == 'stop_detection':
            # 감지 중지 신호
            await self.send(text_data=json.dumps({
                'type': 'detection_status',
                'status': 'stopped',
                'camera_id': self.camera_id
            }))

    # Receive message from room group
    async def detection_update(self, event):
        detection_data = event['data']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'detection_update',
            'data': detection_data
        }))

    async def stream_frame(self, event):
        frame_data = event['data']
        
        # Send frame to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'stream_frame',
            'data': frame_data
        }))

class LiveViewConsumer(AsyncWebsocketConsumer):
    """라이브 뷰 페이지용 WebSocket Consumer - 모든 활성 카메라 모니터링"""
    
    async def connect(self):
        self.room_group_name = 'live_view'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        # 연결 시 활성 카메라 목록 전송
        active_cameras = await self.get_active_cameras()
        await self.send(text_data=json.dumps({
            'type': 'active_cameras',
            'cameras': active_cameras
        }))

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    @database_sync_to_async
    def get_active_cameras(self):
        """활성 카메라 목록 조회"""
        cameras = CameraConfig.objects.filter(is_active=True)
        return [
            {
                'id': camera.id,
                'name': camera.name,
                'rtsp_url': camera.rtsp_url,
                'max_fps': camera.max_fps
            }
            for camera in cameras
        ]

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        
        if message_type == 'start_all_detection':
            # 모든 카메라 감지 시작
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'detection_control',
                    'action': 'start_all'
                }
            )
        elif message_type == 'stop_all_detection':
            # 모든 카메라 감지 중지
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'detection_control',
                    'action': 'stop_all'
                }
            )

    # Receive message from room group
    async def detection_update(self, event):
        """감지 결과 업데이트"""
        await self.send(text_data=json.dumps({
            'type': 'detection_update',
            'data': event['data']
        }))

    async def stream_frame(self, event):
        """스트림 프레임 업데이트"""
        await self.send(text_data=json.dumps({
            'type': 'stream_frame',
            'data': event['data']
        }))

    async def detection_control(self, event):
        """감지 제어 메시지"""
        await self.send(text_data=json.dumps({
            'type': 'detection_control',
            'action': event['action']
        }))

    async def camera_status(self, event):
        """카메라 상태 업데이트"""
        await self.send(text_data=json.dumps({
            'type': 'camera_status',
            'data': event['data']
        }))