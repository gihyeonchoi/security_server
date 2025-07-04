// door_monitor.js
class DoorMonitor {
    constructor() {
        this.autoRefreshInterval = null;
        this.isAutoRefresh = false;
        this.refreshInterval = 5000; // 5초마다 새로고침
        
        this.initializeEventListeners();
        this.updateLastRefreshTime();
    }
    
    initializeEventListeners() {
        // 수동 새로고침 버튼
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshData();
        });
        
        // 자동 새로고침 토글 버튼
        document.getElementById('autoRefreshBtn').addEventListener('click', () => {
            this.toggleAutoRefresh();
        });
        
        // 페이지 로드 시 자동으로 데이터 새로고침
        this.refreshData();
    }
    
    async refreshData() {
        try {
            const response = await fetch('/RFID/door_status_get/');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.updateRoomCards(data.data.rooms);
                this.updateSummary(data.data);
                this.updateLastRefreshTime();
                this.showNotification('데이터가 업데이트되었습니다.', 'success');
            } else {
                this.showNotification('데이터 업데이트에 실패했습니다.', 'error');
            }
        } catch (error) {
            console.error('데이터 새로고침 오류:', error);
            this.showNotification('서버 연결에 실패했습니다.', 'error');
        }
    }
    
    updateRoomCards(rooms) {
        const roomsGrid = document.getElementById('roomsGrid');
        
        if (!rooms || rooms.length === 0) {
            roomsGrid.innerHTML = '<div class="no-rooms"><p>등록된 방이 없습니다.</p></div>';
            return;
        }
        
        roomsGrid.innerHTML = rooms.map(room => {
            const statusClass = room.door_status ? 'open' : 'closed';
            const statusIcon = room.door_status ? '🔓' : '🔒';
            const statusText = room.door_status_text;
            const lastChange = room.last_door_change 
                ? new Date(room.last_door_change).toLocaleString('ko-KR')
                : '변경 이력 없음';
            
            return `
                <div class="room-card ${statusClass}" 
                     data-room-id="${room.id}" 
                     data-device-id="${room.device_id}">
                    <div class="room-header">
                        <h3 class="room-name">${room.name}</h3>
                        <div class="door-status-icon">${statusIcon}</div>
                    </div>
                    <div class="room-info">
                        <p class="location">📍 ${room.location}</p>
                        <p class="device-id">🔧 ${room.device_id}</p>
                        <p class="required-level">🔐 보안등급: ${room.required_level}</p>
                    </div>
                    <div class="room-status">
                        <span class="status-text">${statusText}</span>
                        <span class="last-change">${lastChange}</span>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    updateSummary(data) {
        // 요약 정보 업데이트
        const summaryItems = document.querySelectorAll('.summary-item');
        if (summaryItems.length >= 3) {
            summaryItems[0].querySelector('.count').textContent = data.total_rooms;
            summaryItems[1].querySelector('.count').textContent = data.open_rooms;
            summaryItems[2].querySelector('.count').textContent = data.closed_rooms;
        }
    }
    
    toggleAutoRefresh() {
        const button = document.getElementById('autoRefreshBtn');
        
        if (this.isAutoRefresh) {
            // 자동 새로고침 중지
            clearInterval(this.autoRefreshInterval);
            this.isAutoRefresh = false;
            button.textContent = '자동 새로고침: OFF';
            button.classList.remove('active');
            this.showNotification('자동 새로고침이 중지되었습니다.', 'info');
        } else {
            // 자동 새로고침 시작
            this.autoRefreshInterval = setInterval(() => {
                this.refreshData();
            }, this.refreshInterval);
            this.isAutoRefresh = true;
            button.textContent = '자동 새로고침: ON';
            button.classList.add('active');
            this.showNotification('자동 새로고침이 시작되었습니다.', 'success');
        }
    }
    
    updateLastRefreshTime() {
        const lastUpdate = document.getElementById('lastUpdate');
        lastUpdate.textContent = new Date().toLocaleString('ko-KR');
    }
    
    showNotification(message, type = 'info') {
        // 간단한 알림 표시
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 600;
            z-index: 1000;
            transition: all 0.3s ease;
            opacity: 0;
            transform: translateY(-20px);
        `;
        
        // 타입별 색상 설정
        const colors = {
            success: '#4caf50',
            error: '#f44336',
            warning: '#ff9800',
            info: '#2196f3'
        };
        notification.style.backgroundColor = colors[type] || colors.info;
        
        document.body.appendChild(notification);
        
        // 애니메이션 효과
        setTimeout(() => {
            notification.style.opacity = '1';
            notification.style.transform = 'translateY(0)';
        }, 100);
        
        // 3초 후 자동 제거
        setTimeout(() => {
            notification.style.opacity = '0';
            notification.style.transform = 'translateY(-20px)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
}

// 페이지 로드 시 DoorMonitor 초기화
document.addEventListener('DOMContentLoaded', () => {
    new DoorMonitor();
});