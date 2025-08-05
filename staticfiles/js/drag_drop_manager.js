/**
 * 드래그 앤 드롭 카메라 위치 관리 JavaScript
 * Map Admin System - Camera Position Drag & Drop Manager
 */

class CameraPositionManager {
    constructor() {
        this.isDragging = false;
        this.currentElement = null;
        this.startX = 0;
        this.startY = 0;
        this.mapContainer = null;
        this.init();
    }

    init() {
        // DOM이 로드되면 초기화
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        this.mapContainer = document.getElementById('map-container');
        if (!this.mapContainer) return;

        const draggableElements = document.querySelectorAll('.camera-icon.draggable');
        
        // 각 드래그 가능한 요소에 이벤트 리스너 추가
        draggableElements.forEach(element => {
            element.addEventListener('mousedown', (e) => this.startDrag(e));
            
            // 터치 이벤트 지원 (모바일)
            element.addEventListener('touchstart', (e) => this.startDrag(e), { passive: false });
        });

        // 컨텍스트 메뉴 방지 (우클릭)
        draggableElements.forEach(element => {
            element.addEventListener('contextmenu', e => e.preventDefault());
        });
    }

    startDrag(e) {
        e.preventDefault();
        
        this.isDragging = true;
        this.currentElement = e.target.closest('.camera-icon');
        
        // 터치 이벤트와 마우스 이벤트 구분
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        
        this.startX = clientX;
        this.startY = clientY;
        
        // 드래깅 중 스타일 변경
        this.currentElement.classList.add('dragging');
        this.currentElement.style.zIndex = '1000';
        
        // 전역 이벤트 리스너 추가
        document.addEventListener('mousemove', (e) => this.drag(e));
        document.addEventListener('mouseup', (e) => this.stopDrag(e));
        
        // 터치 이벤트
        document.addEventListener('touchmove', (e) => this.drag(e), { passive: false });
        document.addEventListener('touchend', (e) => this.stopDrag(e));

        // 드래그 중 텍스트 선택 방지
        document.body.style.userSelect = 'none';
        
        this.showTooltip('드래그하여 위치를 조정하세요');
    }

    drag(e) {
        if (!this.isDragging || !this.currentElement) return;

        e.preventDefault();
        
        // 터치 이벤트와 마우스 이벤트 구분
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const clientY = e.touches ? e.touches[0].clientY : e.clientY;
        
        // 지도 컨테이너의 위치와 크기 계산
        const mapRect = this.mapContainer.getBoundingClientRect();
        const mapWidth = mapRect.width;
        const mapHeight = mapRect.height;
        
        // 마우스 위치를 지도 컨테이너 내 상대 위치로 변환
        const relativeX = clientX - mapRect.left;
        const relativeY = clientY - mapRect.top;
        
        // 경계 체크 (여유 공간 20px)
        const margin = 20;
        const boundedX = Math.max(margin, Math.min(relativeX, mapWidth - margin));
        const boundedY = Math.max(margin, Math.min(relativeY, mapHeight - margin));
        
        // 퍼센트로 변환
        const percentX = (boundedX / mapWidth) * 100;
        const percentY = (boundedY / mapHeight) * 100;
        
        // 요소 위치 업데이트
        this.currentElement.style.left = percentX + '%';
        this.currentElement.style.top = percentY + '%';
        
        // 실시간 좌표 표시
        this.updateCoordinateDisplay(percentX, percentY);
    }

    stopDrag(e) {
        if (!this.isDragging || !this.currentElement) return;

        e.preventDefault();
        
        // 스타일 복원
        this.currentElement.classList.remove('dragging');
        this.currentElement.style.zIndex = '10';
        
        // 터치 이벤트와 마우스 이벤트 구분
        const clientX = e.changedTouches ? e.changedTouches[0].clientX : e.clientX;
        const clientY = e.changedTouches ? e.changedTouches[0].clientY : e.clientY;
        
        // 최종 위치 계산
        const mapRect = this.mapContainer.getBoundingClientRect();
        const mapWidth = mapRect.width;
        const mapHeight = mapRect.height;
        
        const relativeX = clientX - mapRect.left;
        const relativeY = clientY - mapRect.top;
        
        const margin = 20;
        const boundedX = Math.max(margin, Math.min(relativeX, mapWidth - margin));
        const boundedY = Math.max(margin, Math.min(relativeY, mapHeight - margin));
        
        const percentX = (boundedX / mapWidth) * 100;
        const percentY = (boundedY / mapHeight) * 100;
        
        // 서버에 위치 업데이트 전송
        this.updateCameraPosition(
            this.currentElement.dataset.positionId, 
            percentX, 
            percentY
        );
        
        // 이벤트 리스너 제거
        document.removeEventListener('mousemove', this.drag);
        document.removeEventListener('mouseup', this.stopDrag);
        document.removeEventListener('touchmove', this.drag);
        document.removeEventListener('touchend', this.stopDrag);
        
        // 텍스트 선택 복원
        document.body.style.userSelect = '';
        
        this.isDragging = false;
        this.currentElement = null;
        
        this.hideTooltip();
    }

    async updateCameraPosition(positionId, x, y) {
        const url = `/map/camera-positions/${positionId}/update-position/`;
        
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCookie('csrftoken')
                },
                body: JSON.stringify({
                    x_position: parseFloat(x.toFixed(2)),
                    y_position: parseFloat(y.toFixed(2))
                })
            });

            const data = await response.json();
            
            if (data.status === 'success') {
                this.showMessage(data.message, 'success');
                this.updateSidebarPosition(positionId, x, y);
                this.addToHistory(positionId, x, y);
            } else {
                this.showMessage(data.message, 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            this.showMessage('위치 업데이트 중 오류가 발생했습니다.', 'error');
        }
    }

    updateSidebarPosition(positionId, x, y) {
        const cameraElement = document.querySelector(`[data-position-id="${positionId}"]`);
        if (!cameraElement) return;

        const cameraName = cameraElement.dataset.cameraName;
        const listItems = document.querySelectorAll('.list-group-item');
        
        listItems.forEach(item => {
            if (item.textContent.includes(cameraName)) {
                const small = item.querySelector('small');
                if (small) {
                    small.textContent = `(${x.toFixed(1)}%, ${y.toFixed(1)}%)`;
                    small.style.color = '#28a745';
                    setTimeout(() => {
                        small.style.color = '';
                    }, 2000);
                }
            }
        });
    }

    updateCoordinateDisplay(x, y) {
        let coordDisplay = document.getElementById('coord-display');
        if (!coordDisplay) {
            coordDisplay = document.createElement('div');
            coordDisplay.id = 'coord-display';
            coordDisplay.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                z-index: 9999;
                pointer-events: none;
            `;
            document.body.appendChild(coordDisplay);
        }
        
        coordDisplay.textContent = `X: ${x.toFixed(1)}%, Y: ${y.toFixed(1)}%`;
        coordDisplay.style.display = 'block';
    }

    showMessage(message, type) {
        const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
        const icon = type === 'success' ? '✅' : '❌';
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
        `;
        
        alertDiv.innerHTML = `
            ${icon} ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        // 자동 제거
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 3000);
    }

    showTooltip(message) {
        let tooltip = document.getElementById('drag-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'drag-tooltip';
            tooltip.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 10px 20px;
                border-radius: 25px;
                font-size: 14px;
                font-weight: 600;
                z-index: 9998;
                pointer-events: none;
                opacity: 0;
                transition: opacity 0.3s ease;
            `;
            document.body.appendChild(tooltip);
        }
        
        tooltip.textContent = message;
        tooltip.style.opacity = '1';
    }

    hideTooltip() {
        const tooltip = document.getElementById('drag-tooltip');
        const coordDisplay = document.getElementById('coord-display');
        
        if (tooltip) {
            tooltip.style.opacity = '0';
            setTimeout(() => tooltip.remove(), 300);
        }
        
        if (coordDisplay) {
            coordDisplay.style.display = 'none';
        }
    }

    addToHistory(positionId, x, y) {
        const cameraElement = document.querySelector(`[data-position-id="${positionId}"]`);
        const cameraName = cameraElement ? cameraElement.dataset.cameraName : 'Unknown';
        
        const history = JSON.parse(localStorage.getItem('cameraPositionHistory') || '[]');
        history.unshift({
            positionId,
            cameraName,
            x: x.toFixed(2),
            y: y.toFixed(2),
            timestamp: new Date().toISOString()
        });
        
        // 최대 10개 항목만 유지
        if (history.length > 10) {
            history.splice(10);
        }
        
        localStorage.setItem('cameraPositionHistory', JSON.stringify(history));
    }

    getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
}

// 키보드 단축키 지원
document.addEventListener('keydown', (e) => {
    // ESC 키로 드래그 취소
    if (e.key === 'Escape') {
        const manager = window.cameraPositionManager;
        if (manager && manager.isDragging) {
            manager.stopDrag(e);
        }
    }
    
    // Ctrl+Z로 마지막 변경 취소 (향후 구현 가능)
    if (e.ctrlKey && e.key === 'z') {
        // TODO: 실행 취소 기능
        console.log('Undo functionality can be implemented here');
    }
});

// 전역 객체로 설정
window.CameraPositionManager = CameraPositionManager;

// 자동 초기화
if (document.querySelector('.camera-icon.draggable')) {
    window.cameraPositionManager = new CameraPositionManager();
}