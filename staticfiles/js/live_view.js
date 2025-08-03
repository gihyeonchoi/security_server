// CCTV/static/js/live_view.js - WebSocket + InferencePipeline 버전

let cameraWebSockets = {};
let cameraStreams = {};
let activeFullscreen = null;
let liveViewWebSocket = null;

// WebSocket 기반 초기화 함수
function initializeLiveViewWithWebSocket(configs) {
    console.log('Initializing WebSocket live view with configs:', configs);
    
    // 각 카메라에 대해 WebSocket 연결 초기화
    Object.keys(configs).forEach(cameraId => {
        initializeCameraWebSocket(cameraId, configs[cameraId]);
    });
    
    // 라이브 뷰 전체 WebSocket 연결
    initializeLiveViewWebSocket();
    
    // 레이아웃 변경 이벤트
    document.getElementById('layoutSelect').addEventListener('change', changeLayout);
    
    // 전체 제어 버튼 이벤트
    document.getElementById('toggleAllDetection').addEventListener('click', startAllDetection);
    document.getElementById('stopAllDetection').addEventListener('click', stopAllDetection);
    
    // 페이지 종료 시 WebSocket 정리
    window.addEventListener('beforeunload', cleanup);
}

// 개별 카메라 WebSocket 초기화
function initializeCameraWebSocket(cameraId, config) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    const loadingOverlay = document.getElementById(`loading-${cameraId}`);
    const statusIndicator = document.getElementById(`status-${cameraId}`);
    const wsStatusIndicator = document.getElementById(`ws-status-${cameraId}`);
    
    // 카메라 스트림 객체 생성
    cameraStreams[cameraId] = {
        config: config,
        canvas: canvas,
        isPlaying: true,
        lastFrame: null,
        detectionCount: 0
    };
    
    // WebSocket 연결 (ASGI 서버 포트 8001 사용)
    const wsUrl = `ws://127.0.0.1:8001/ws/cctv/camera/${cameraId}/`;
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    
    const ws = new WebSocket(wsUrl);
    cameraWebSockets[cameraId] = ws;
    
    ws.onopen = function(event) {
        console.log(`Camera ${cameraId} WebSocket connected`);
        wsStatusIndicator.textContent = '🟢';
        wsStatusIndicator.title = 'WebSocket 연결됨';
        loadingOverlay.classList.add('hidden');
        
        // Canvas 초기화
        initializeCanvas(cameraId);
        
        // Pipeline 상태 확인
        checkPipelineStatus(cameraId);
        
        // 기본 영상 표시 (RTSP 스트림이 있는 경우)
        if (config.rtspUrl) {
            showBasicVideoStream(cameraId, config);
        }
    };
    
    ws.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            console.log(`📨 카메라 ${cameraId} WebSocket 메시지 수신:`, data);
            handleWebSocketMessage(cameraId, data);
        } catch (error) {
            console.error(`❌ 카메라 ${cameraId} WebSocket 메시지 파싱 오류:`, error, event.data);
        }
    };
    
    ws.onclose = function(event) {
        console.log(`Camera ${cameraId} WebSocket disconnected`);
        wsStatusIndicator.textContent = '🔴';
        wsStatusIndicator.title = 'WebSocket 연결 끊김';
        
        // 재연결 시도
        setTimeout(() => {
            if (!cameraWebSockets[cameraId] || cameraWebSockets[cameraId].readyState === WebSocket.CLOSED) {
                initializeCameraWebSocket(cameraId, config);
            }
        }, 3000);
    };
    
    ws.onerror = function(error) {
        console.error(`Camera ${cameraId} WebSocket error:`, error);
        wsStatusIndicator.textContent = '🟡';
        wsStatusIndicator.title = 'WebSocket 오류';
    };
}

// 라이브 뷰 전체 WebSocket 초기화
function initializeLiveViewWebSocket() {
    const wsUrl = `ws://127.0.0.1:8001/ws/cctv/live/`;
    console.log(`Connecting to Live View WebSocket: ${wsUrl}`);
    
    liveViewWebSocket = new WebSocket(wsUrl);
    
    liveViewWebSocket.onopen = function(event) {
        console.log('Live View WebSocket connected');
        
        // 전체 Pipeline 상태 확인
        checkAllPipelineStatus();
        
        // 자동으로 모든 카메라 감지 시작
        setTimeout(() => {
            console.log('Auto-starting all camera detection...');
            startAllDetection();
        }, 1000); // 1초 후 자동 시작
    };
    
    liveViewWebSocket.onmessage = function(event) {
        const data = JSON.parse(event.data);
        handleLiveViewMessage(data);
    };
    
    liveViewWebSocket.onclose = function(event) {
        console.log('Live View WebSocket disconnected');
        // 재연결 시도
        setTimeout(() => {
            if (!liveViewWebSocket || liveViewWebSocket.readyState === WebSocket.CLOSED) {
                initializeLiveViewWebSocket();
            }
        }, 3000);
    };
    
    liveViewWebSocket.onerror = function(error) {
        console.error('Live View WebSocket error:', error);
    };
}

// WebSocket 메시지 처리
function handleWebSocketMessage(cameraId, data) {
    switch(data.type) {
        case 'detection_update':
            updateDetectionDisplay(cameraId, data.data);
            break;
        case 'stream_frame':
            updateFrameDisplay(cameraId, data.data);
            break;
        case 'detection_status':
            updateDetectionStatus(cameraId, data.status);
            break;
        default:
            console.log(`Unknown message type: ${data.type}`);
    }
}

// 라이브 뷰 메시지 처리
function handleLiveViewMessage(data) {
    switch(data.type) {
        case 'detection_update':
            updateDetectionDisplay(data.data.camera_id, data.data);
            break;
        case 'detection_control':
            handleDetectionControl(data.action);
            break;
        case 'camera_status':
            updateCameraStatus(data.data);
            break;
        default:
            console.log(`Unknown live view message: ${data.type}`);
    }
}

// 감지 결과 표시 업데이트
function updateDetectionDisplay(cameraId, detectionData) {
    const objectCount = document.getElementById(`object-count-${cameraId}`);
    const detectionList = document.getElementById(`detection-list-${cameraId}`);
    const lastUpdate = document.getElementById(`last-update-${cameraId}`);
    const canvas = document.getElementById(`canvas-${cameraId}`);
    
    console.log(`📊 카메라 ${cameraId} 감지 데이터:`, detectionData);
    
    if (!detectionData) return;
    
    // Pipeline이 실행 중임을 표시
    updateDetectionStatus(cameraId, 'started');
    
    // 객체 수 업데이트
    const detectionCount = detectionData.detection_count || (detectionData.detections ? detectionData.detections.length : 0);
    objectCount.textContent = detectionCount;
    
    // 마지막 업데이트 시간
    lastUpdate.textContent = new Date(detectionData.timestamp * 1000).toLocaleTimeString();
    
    // 감지 결과가 있는 경우
    if (detectionData.detections && detectionData.detections.length > 0) {
        // 클래스별 집계
        const classes = {};
        detectionData.detections.forEach(d => {
            classes[d.class] = (classes[d.class] || 0) + 1;
        });
        
        // 리스트 업데이트
        detectionList.innerHTML = Object.entries(classes)
            .map(([cls, count]) => `${cls}: ${count}`)
            .join(', ');
    } else {
        detectionList.innerHTML = '감지된 객체 없음';
    }
    
    // 프레임 데이터가 있다면 캔버스에 표시
    if (detectionData.frame_data) {
        console.log(`🖼️ 카메라 ${cameraId} 프레임 데이터 수신, 캔버스 업데이트`);
        displayFrameOnCanvas(cameraId, detectionData.frame_data, detectionData.detections);
    } else {
        console.log(`⚠️ 카메라 ${cameraId} 프레임 데이터 없음`);
        // 프레임 데이터가 없어도 Pipeline이 실행 중임을 표시
        showPipelineRunningStatus(cameraId);
    }
    
    // 스트림 객체 업데이트
    if (cameraStreams[cameraId]) {
        cameraStreams[cameraId].detectionCount = detectionCount;
    }
}

// 캔버스에 프레임 표시
function displayFrameOnCanvas(cameraId, frameData, detections) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    if (!canvas || !frameData) return;
    
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    img.onload = function() {
        // 캔버스 크기를 고정 (640x480)
        canvas.width = 640;
        canvas.height = 480;
        
        // 이미지 비율 유지하며 캔버스에 맞게 그리기
        const imgAspect = img.width / img.height;
        const canvasAspect = canvas.width / canvas.height;
        
        let drawWidth, drawHeight, offsetX, offsetY;
        
        if (imgAspect > canvasAspect) {
            // 이미지가 더 넓음 - 너비에 맞춤
            drawWidth = canvas.width;
            drawHeight = canvas.width / imgAspect;
            offsetX = 0;
            offsetY = (canvas.height - drawHeight) / 2;
        } else {
            // 이미지가 더 높음 - 높이에 맞춤
            drawWidth = canvas.height * imgAspect;
            drawHeight = canvas.height;
            offsetX = (canvas.width - drawWidth) / 2;
            offsetY = 0;
        }
        
        // 배경 지우기
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // 이미지 그리기
        ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
        
        // 감지 결과 오버레이
        if (detections && detections.length > 0) {
            drawDetectionsOnCanvas(ctx, detections, drawWidth, drawHeight, offsetX, offsetY);
        }
        
        // 상태 업데이트
        const statusIndicator = document.getElementById(`status-${cameraId}`);
        if (statusIndicator) {
            statusIndicator.className = 'status-indicator online';
        }
    };
    
    img.onerror = function() {
        console.error(`Failed to load frame for camera ${cameraId}`);
        showBasicVideoStream(cameraId, cameraStreams[cameraId].config);
    };
    
    img.src = frameData;
}

// 캔버스에 감지 결과 그리기
function drawDetectionsOnCanvas(ctx, detections, drawWidth, drawHeight, offsetX, offsetY) {
    ctx.strokeStyle = '#00ff00';
    ctx.lineWidth = 2;
    ctx.fillStyle = '#00ff00';
    ctx.font = '14px Arial';
    
    detections.forEach(detection => {
        // 감지 좌표를 그려진 이미지 영역에 맞게 스케일링
        const scaleX = drawWidth / 640; // 원본 이미지 너비 기준
        const scaleY = drawHeight / 480; // 원본 이미지 높이 기준
        
        const x = (detection.x - detection.width / 2) * scaleX + offsetX;
        const y = (detection.y - detection.height / 2) * scaleY + offsetY;
        const boxWidth = detection.width * scaleX;
        const boxHeight = detection.height * scaleY;
        
        // 바운딩 박스 그리기
        ctx.strokeRect(x, y, boxWidth, boxHeight);
        
        // 레이블 그리기
        const confidence = detection.confidence || 0;
        const label = `${detection.class} ${(confidence * 100).toFixed(1)}%`;
        const labelWidth = ctx.measureText(label).width;
        
        // 레이블 배경
        ctx.fillStyle = '#00ff00';
        ctx.fillRect(x, y - 20, labelWidth + 4, 20);
        
        // 레이블 텍스트
        ctx.fillStyle = '#000000';
        ctx.fillText(label, x + 2, y - 5);
        ctx.fillStyle = '#00ff00';
    });
}

// 감지 상태 업데이트
function updateDetectionStatus(cameraId, status) {
    const pipelineStatus = document.getElementById(`pipeline-status-${cameraId}`);
    const toggleButton = document.getElementById(`detection-toggle-${cameraId}`);
    
    if (status === 'started') {
        pipelineStatus.textContent = '실행 중';
        pipelineStatus.style.color = '#28a745';
        toggleButton.textContent = '⏸️';
    } else {
        pipelineStatus.textContent = '중지됨';
        pipelineStatus.style.color = '#dc3545';
        toggleButton.textContent = '▶️';
    }
}

// 카메라 상태 업데이트
function updateCameraStatus(statusData) {
    // 카메라 상태 정보 업데이트 로직
    console.log('Camera status update:', statusData);
}

// 감지 제어 처리
function handleDetectionControl(action) {
    const allButton = document.getElementById('toggleAllDetection');
    const stopButton = document.getElementById('stopAllDetection');
    
    if (action === 'start_all') {
        allButton.textContent = '전체 AI 분석 실행 중';
        allButton.disabled = true;
        stopButton.disabled = false;
    } else if (action === 'stop_all') {
        allButton.textContent = '전체 AI 분석 시작';
        allButton.disabled = false;
        stopButton.disabled = true;
    }
}

// 개별 카메라 감지 토글
function toggleDetection(cameraId) {
    const ws = cameraWebSockets[cameraId];
    const pipelineStatus = document.getElementById(`pipeline-status-${cameraId}`);
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        const currentStatus = pipelineStatus.textContent;
        
        if (currentStatus === '중지됨') {
            // 감지 시작
            startCameraDetection(cameraId);
        } else {
            // 감지 중지
            stopCameraDetection(cameraId);
        }
    } else {
        console.error(`WebSocket for camera ${cameraId} is not connected`);
    }
}

// 개별 카메라 감지 시작
async function startCameraDetection(cameraId) {
    try {
        const response = await fetch(`/CCTV/detection/${cameraId}/start/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            console.log(`Camera ${cameraId} detection started`);
            updateDetectionStatus(cameraId, 'started');
        }
    } catch (error) {
        console.error(`Error starting detection for camera ${cameraId}:`, error);
    }
}

// 개별 카메라 감지 중지
async function stopCameraDetection(cameraId) {
    try {
        const response = await fetch(`/CCTV/detection/${cameraId}/stop/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            console.log(`Camera ${cameraId} detection stopped`);
            updateDetectionStatus(cameraId, 'stopped');
        }
    } catch (error) {
        console.error(`Error stopping detection for camera ${cameraId}:`, error);
    }
}

// 전체 감지 시작
async function startAllDetection() {
    try {
        const response = await fetch('/CCTV/detection/start-all/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            console.log('All cameras detection started');
            
            // 모든 카메라 상태 업데이트
            Object.keys(cameraStreams).forEach(cameraId => {
                updateDetectionStatus(cameraId, 'started');
            });
        }
    } catch (error) {
        console.error('Error starting all detection:', error);
    }
}

// 전체 감지 중지
async function stopAllDetection() {
    try {
        const response = await fetch('/CCTV/detection/stop-all/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        });
        
        const data = await response.json();
        if (data.status === 'success') {
            console.log('All cameras detection stopped');
            
            // 모든 카메라 상태 업데이트
            Object.keys(cameraStreams).forEach(cameraId => {
                updateDetectionStatus(cameraId, 'stopped');
            });
        }
    } catch (error) {
        console.error('Error stopping all detection:', error);
    }
}

// 전체화면 (WebSocket 버전)
function fullscreenCamera(cameraId) {
    const modal = document.getElementById('fullscreenModal');
    const title = document.getElementById('fullscreenTitle');
    const fullscreenCanvas = document.getElementById('fullscreenCanvas');
    
    title.textContent = cameraStreams[cameraId].config.name;
    modal.classList.add('active');
    activeFullscreen = cameraId;
    
    // 현재 캔버스 내용을 전체화면으로 복사
    const sourceCanvas = document.getElementById(`canvas-${cameraId}`);
    if (sourceCanvas) {
        const ctx = fullscreenCanvas.getContext('2d');
        fullscreenCanvas.width = sourceCanvas.width;
        fullscreenCanvas.height = sourceCanvas.height;
        ctx.drawImage(sourceCanvas, 0, 0);
    }
}

// 전체화면 닫기
function closeFullscreen() {
    const modal = document.getElementById('fullscreenModal');
    modal.classList.remove('active');
    activeFullscreen = null;
}

// 스냅샷 캡처 (WebSocket 버전)
function captureSnapshot(cameraId) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    
    if (canvas && canvas.width > 0 && canvas.height > 0) {
        // 다운로드
        const link = document.createElement('a');
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        link.download = `camera_${cameraId}_${timestamp}.png`;
        link.href = canvas.toDataURL();
        link.click();
    } else {
        console.warn(`No frame available for camera ${cameraId}`);
    }
}

// CSRF 토큰 가져오기
function getCsrfToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
}

// Pipeline 상태 확인
async function checkPipelineStatus(cameraId) {
    try {
        const response = await fetch(`/CCTV/detection/${cameraId}/`);
        const data = await response.json();
        
        console.log(`Camera ${cameraId} pipeline status:`, data);
        
        if (data.pipeline_running) {
            updateDetectionStatus(cameraId, 'started');
        } else {
            updateDetectionStatus(cameraId, 'stopped');
            // 사용자에게 시작 버튼을 누르라고 안내
            showPipelineHint(cameraId);
        }
    } catch (error) {
        console.error(`Error checking pipeline status for camera ${cameraId}:`, error);
    }
}

// Pipeline 힌트 표시
function showPipelineHint(cameraId) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    const ctx = canvas.getContext('2d');
    
    // Canvas 크기 설정
    canvas.width = 640;
    canvas.height = 480;
    
    // 배경 그리기
    ctx.fillStyle = '#2a2a2a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 텍스트 그리기
    ctx.fillStyle = '#ffffff';
    ctx.font = '20px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('Pipeline 중지됨', canvas.width / 2, canvas.height / 2 - 40);
    
    ctx.font = '16px Arial';
    ctx.fillStyle = '#888888';
    ctx.fillText('▶️ 버튼을 눌러 감지를 시작하세요', canvas.width / 2, canvas.height / 2);
    ctx.fillText('또는 "전체 AI 분석 시작" 버튼을 사용하세요', canvas.width / 2, canvas.height / 2 + 30);
}

// 전체 Pipeline 상태 확인
async function checkAllPipelineStatus() {
    try {
        const response = await fetch('/CCTV/detection/status/');
        const data = await response.json();
        
        console.log('All pipelines status:', data);
        
        if (data.active_count > 0) {
            document.getElementById('toggleAllDetection').textContent = '전체 AI 분석 실행 중';
            document.getElementById('toggleAllDetection').disabled = true;
            document.getElementById('stopAllDetection').disabled = false;
        } else {
            document.getElementById('toggleAllDetection').textContent = '전체 AI 분석 시작';
            document.getElementById('toggleAllDetection').disabled = false;
            document.getElementById('stopAllDetection').disabled = true;
        }
    } catch (error) {
        console.error('Error checking all pipeline status:', error);
    }
}

// Canvas 초기화
function initializeCanvas(cameraId) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    if (!canvas) return;
    
    // Canvas 크기 설정
    canvas.width = 640;
    canvas.height = 480;
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    
    const ctx = canvas.getContext('2d');
    
    // 초기 검은 배경
    ctx.fillStyle = '#000000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    console.log(`✅ 카메라 ${cameraId} Canvas 초기화 완료: ${canvas.width}x${canvas.height}`);
}

// 기본 비디오 스트림 표시 (Pipeline 시작 전)
function showBasicVideoStream(cameraId, config) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    
    // Canvas 크기 설정
    canvas.width = 640;
    canvas.height = 480;
    
    const ctx = canvas.getContext('2d');
    
    // 기본 배경 그리기
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 카메라 정보 표시
    ctx.fillStyle = '#ffffff';
    ctx.font = '24px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(config.name, canvas.width / 2, 100);
    
    ctx.font = '16px Arial';
    ctx.fillStyle = '#888888';
    ctx.fillText('실시간 RTSP 스트림', canvas.width / 2, 130);
    ctx.fillText(`해상도: ${canvas.width}x${canvas.height}`, canvas.width / 2, 160);
    ctx.fillText(`최대 FPS: ${config.maxFps}`, canvas.width / 2, 190);
    
    // Pipeline 상태 표시
    ctx.fillStyle = '#ff6b6b';
    ctx.font = '20px Arial';
    ctx.fillText('🔴 Pipeline 중지됨', canvas.width / 2, canvas.height / 2);
    
    ctx.font = '14px Arial';
    ctx.fillStyle = '#888888';
    ctx.fillText('자동으로 AI 분석을 시작합니다...', canvas.width / 2, canvas.height / 2 + 40);
    
    // RTSP URL 표시 (일부만)
    if (config.rtspUrl) {
        const urlPreview = config.rtspUrl.substring(0, 50) + '...';
        ctx.fillStyle = '#555555';
        ctx.font = '12px monospace';
        ctx.fillText(`RTSP: ${urlPreview}`, canvas.width / 2, canvas.height - 30);
    }
}

// Pipeline 실행 중 상태 표시 (프레임 데이터 없음)
function showPipelineRunningStatus(cameraId) {
    const canvas = document.getElementById(`canvas-${cameraId}`);
    const config = cameraStreams[cameraId]?.config;
    
    if (!canvas || !config) return;
    
    // Canvas 크기 설정
    canvas.width = 640;
    canvas.height = 480;
    
    const ctx = canvas.getContext('2d');
    
    // 기본 배경 그리기
    ctx.fillStyle = '#1a1a1a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // 카메라 정보 표시
    ctx.fillStyle = '#ffffff';
    ctx.font = '24px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(config.name, canvas.width / 2, 100);
    
    ctx.font = '16px Arial';
    ctx.fillStyle = '#888888';
    ctx.fillText('실시간 RTSP 스트림', canvas.width / 2, 130);
    
    // Pipeline 실행 중 표시
    ctx.fillStyle = '#28a745';
    ctx.font = '20px Arial';
    ctx.fillText('🟢 Pipeline 실행 중', canvas.width / 2, canvas.height / 2);
    
    ctx.font = '14px Arial';
    ctx.fillStyle = '#888888';
    ctx.fillText('RTSP 스트림에서 영상을 읽어오는 중...', canvas.width / 2, canvas.height / 2 + 40);
    ctx.fillText('잠시만 기다려주세요', canvas.width / 2, canvas.height / 2 + 65);
    
    // 현재 시간 표시
    const now = new Date().toLocaleTimeString();
    ctx.fillStyle = '#666666';
    ctx.font = '12px monospace';
    ctx.fillText(`마지막 업데이트: ${now}`, canvas.width / 2, canvas.height - 50);
    
    // RTSP URL 표시
    if (config.rtspUrl) {
        const urlPreview = config.rtspUrl.substring(0, 50) + '...';
        ctx.fillText(`RTSP: ${urlPreview}`, canvas.width / 2, canvas.height - 30);
    }
}

// 정리 함수
function cleanup() {
    // 모든 WebSocket 연결 종료
    Object.values(cameraWebSockets).forEach(ws => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.close();
        }
    });
    
    if (liveViewWebSocket && liveViewWebSocket.readyState === WebSocket.OPEN) {
        liveViewWebSocket.close();
    }
}

// 레이아웃 변경
function changeLayout() {
    const grid = document.getElementById('cameraGrid');
    const layout = document.getElementById('layoutSelect').value;
    
    grid.className = `camera-live-grid grid-${layout}`;
}

// ESC 키로 전체화면 닫기
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && activeFullscreen) {
        closeFullscreen();
    }
});