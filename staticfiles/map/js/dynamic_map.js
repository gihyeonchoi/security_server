/**
 * 동적 지도 시스템 JavaScript
 * Map System - Dynamic Floor and Camera Management
 */

class DynamicMapSystem {
    constructor() {
        this.currentFloorId = null;
        this.currentFloorNumber = 1;
        this.locationApiUrl = '/map/location/';
        this.updateInterval = 3000;
        this.locationUpdateTimer = null;
        this.init();
    }

    init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.setup());
        } else {
            this.setup();
        }
    }

    setup() {
        // DOM 요소 초기화
        this.locationDot = document.getElementById('location-dot');
        this.statusDiv = document.getElementById('status');
        this.floorButtons = document.querySelectorAll('#controls button');
        this.cameraIcons = document.querySelectorAll('.camera-icon');
        this.locationSelect = document.getElementById('location-select');

        // 초기 층 설정
        const firstFloorButton = document.querySelector('#controls button.active');
        if (firstFloorButton) {
            this.currentFloorId = parseInt(firstFloorButton.dataset.floor);
            this.currentFloorNumber = parseInt(firstFloorButton.dataset.floorNumber);
        }

        this.setupEventListeners();
        this.startLocationTracking();
    }

    setupEventListeners() {
        // 층 변경 버튼 이벤트
        this.floorButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const floorId = parseInt(btn.dataset.floor);
                const floorNumber = parseInt(btn.dataset.floorNumber);
                this.changeFloor(floorId, floorNumber);
            });
        });

        // 카메라 아이콘 클릭 이벤트
        this.cameraIcons.forEach(icon => {
            icon.addEventListener('click', (event) => {
                const url = event.currentTarget.dataset.url;
                const cameraName = event.currentTarget.dataset.cameraName;
                
                if (url && url !== '#') {
                    this.openCameraStream(url, cameraName);
                } else {
                    this.showMessage('카메라 스트림을 사용할 수 없습니다.', 'warning');
                }
            });

            // 카메라 아이콘 호버 효과
            icon.addEventListener('mouseenter', (event) => {
                const cameraName = event.currentTarget.dataset.cameraName;
                if (cameraName) {
                    this.showCameraTooltip(event.currentTarget, cameraName);
                }
            });

            icon.addEventListener('mouseleave', () => {
                this.hideCameraTooltip();
            });
        });

        // 위치 선택 드롭다운 이벤트
        if (this.locationSelect) {
            this.locationSelect.addEventListener('change', (e) => {
                this.changeLocation(e.target.value);
            });
        }

        // 키보드 단축키
        document.addEventListener('keydown', (e) => {
            this.handleKeyboard(e);
        });

        // 리사이즈 이벤트
        window.addEventListener('resize', () => {
            this.updateLocation();
        });
    }

    changeFloor(floorId, floorNumber) {
        this.currentFloorId = floorId;
        this.currentFloorNumber = floorNumber;
        
        // 모든 지도 숨기기
        document.querySelectorAll('#map-container img').forEach(img => {
            img.classList.add('hidden');
        });
        
        // 선택된 층 지도 보이기
        const activeMap = document.getElementById(`floor${floorId}-map`);
        if (activeMap) {
            activeMap.classList.remove('hidden');
        }
        
        // 버튼 상태 업데이트
        this.floorButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.floor == floorId);
        });
        
        // 카메라 아이콘 보이기/숨기기
        this.cameraIcons.forEach(icon => {
            const iconFloorId = icon.dataset.floorId;
            icon.classList.toggle('hidden', iconFloorId != floorId);
        });

        // 위치 업데이트
        this.updateLocation();
        
        // 층 변경 애니메이션
        this.animateFloorChange();
    }

    changeLocation(locationId) {
        const currentUrl = new URL(window.location);
        currentUrl.searchParams.set('location', locationId);
        window.location.href = currentUrl.toString();
    }

    getCurrentFloorGPS() {
        const activeMap = document.querySelector('#map-container img:not(.hidden)');
        if (!activeMap) return null;
        
        const topLeftLat = parseFloat(activeMap.dataset.topLeftLat);
        const topLeftLon = parseFloat(activeMap.dataset.topLeftLon);
        const bottomRightLat = parseFloat(activeMap.dataset.bottomRightLat);
        const bottomRightLon = parseFloat(activeMap.dataset.bottomRightLon);
        
        if (isNaN(topLeftLat) || isNaN(topLeftLon) || isNaN(bottomRightLat) || isNaN(bottomRightLon)) {
            return null;
        }
        
        return {
            topLeft: { lat: topLeftLat, lon: topLeftLon },
            bottomRight: { lat: bottomRightLat, lon: bottomRightLon }
        };
    }

    mapGpsToPixels(lat, lon) {
        const gpsData = this.getCurrentFloorGPS();
        if (!gpsData) {
            return null;
        }
        
        const activeMap = document.querySelector('#map-container img:not(.hidden)');
        if (!activeMap) return null;
        
        const mapWidth = activeMap.offsetWidth;
        const mapHeight = activeMap.offsetHeight;

        if (mapWidth === 0 || mapHeight === 0) {
            return null;
        }
        
        const latRange = gpsData.topLeft.lat - gpsData.bottomRight.lat;
        const lonRange = gpsData.bottomRight.lon - gpsData.topLeft.lon;
        if (latRange <= 0 || lonRange <= 0) return null;

        const latFraction = (gpsData.topLeft.lat - lat) / latRange;
        const lonFraction = (lon - gpsData.topLeft.lon) / lonRange;
        
        const pixelX = lonFraction * mapWidth;
        const pixelY = latFraction * mapHeight;

        if (pixelX >= 0 && pixelX <= mapWidth && pixelY >= 0 && pixelY <= mapHeight) {
            return { x: pixelX, y: pixelY };
        }
        return null;
    }

    async updateLocation() {
        try {
            const response = await fetch(this.locationApiUrl);
            
            if (!response.ok) throw new Error(`서버 응답 오류: ${response.status}`);
            
            const locationData = await response.json();
            
            if (locationData.latitude === null || locationData.longitude === null || locationData.altitude === null) {
                throw new Error("서버에 아직 유효한 위치 정보가 없습니다.");
            }

            if (locationData.altitude == this.currentFloorNumber) {
                this.statusDiv.textContent = `위치 수신: ${locationData.altitude}층 (현재 층과 일치)`;
                const pixelCoords = this.mapGpsToPixels(locationData.latitude, locationData.longitude);
                
                if (pixelCoords) {
                    this.updateLocationDot(pixelCoords.x, pixelCoords.y);
                } else {
                    this.hideLocationDot();
                    this.statusDiv.textContent += ' (지도 범위 벗어남 또는 GPS 데이터 없음)';
                }
            } else {
                this.hideLocationDot();
                this.statusDiv.textContent = `위치 수신: ${locationData.altitude}층 (현재 ${this.currentFloorNumber}층과 달라 숨김)`;
            }
        } catch (error) {
            console.error('위치 정보 업데이트 실패:', error);
            this.statusDiv.textContent = error.message;
            this.hideLocationDot();
        }
    }

    updateLocationDot(x, y) {
        if (!this.locationDot) return;
        
        this.locationDot.style.left = `${x}px`;
        this.locationDot.style.top = `${y}px`;
        this.locationDot.style.display = 'block';
        
        // 애니메이션 효과
        this.locationDot.style.transform = 'translate(-50%, -50%) scale(1.2)';
        setTimeout(() => {
            this.locationDot.style.transform = 'translate(-50%, -50%) scale(1)';
        }, 200);
    }

    hideLocationDot() {
        if (this.locationDot) {
            this.locationDot.style.display = 'none';
        }
    }

    openCameraStream(url, cameraName) {
        // 새 창에서 카메라 스트림 열기
        const newWindow = window.open(url, '_blank', 'width=800,height=600,scrollbars=yes,resizable=yes');
        
        if (newWindow) {
            this.showMessage(`${cameraName} 스트림을 새 창에서 열었습니다.`, 'success');
        } else {
            this.showMessage('팝업이 차단되었습니다. 브라우저 설정을 확인해주세요.', 'warning');
        }
    }

    showCameraTooltip(element, cameraName) {
        let tooltip = document.getElementById('camera-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'camera-tooltip';
            tooltip.style.cssText = `
                position: absolute;
                background: rgba(0, 0, 0, 0.9);
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                z-index: 1000;
                pointer-events: none;
                white-space: nowrap;
            `;
            document.body.appendChild(tooltip);
        }
        
        tooltip.textContent = `📹 ${cameraName}`;
        
        const rect = element.getBoundingClientRect();
        tooltip.style.left = (rect.left + rect.width / 2) + 'px';
        tooltip.style.top = (rect.top - 40) + 'px';
        tooltip.style.transform = 'translateX(-50%)';
        tooltip.style.display = 'block';
    }

    hideCameraTooltip() {
        const tooltip = document.getElementById('camera-tooltip');
        if (tooltip) {
            tooltip.style.display = 'none';
        }
    }

    animateFloorChange() {
        const mapContainer = document.getElementById('map-container');
        if (!mapContainer) return;
        
        mapContainer.style.transform = 'scale(0.98)';
        mapContainer.style.opacity = '0.8';
        
        setTimeout(() => {
            mapContainer.style.transform = 'scale(1)';
            mapContainer.style.opacity = '1';
        }, 150);
    }

    showMessage(message, type = 'info') {
        const alertClass = {
            'success': 'alert-success',
            'warning': 'alert-warning',
            'error': 'alert-danger',
            'info': 'alert-info'
        }[type] || 'alert-info';
        
        const icon = {
            'success': '✅',
            'warning': '⚠️',
            'error': '❌',
            'info': 'ℹ️'
        }[type] || 'ℹ️';
        
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = `
            top: 20px;
            right: 20px;
            z-index: 9999;
            min-width: 300px;
            max-width: 400px;
        `;
        
        alertDiv.innerHTML = `
            ${icon} ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 4000);
    }

    handleKeyboard(e) {
        // 숫자 키로 층 변경
        const keyNum = parseInt(e.key);
        if (keyNum >= 1 && keyNum <= 9) {
            const targetButton = Array.from(this.floorButtons).find(btn => 
                parseInt(btn.dataset.floorNumber) === keyNum
            );
            if (targetButton) {
                targetButton.click();
            }
        }
        
        // 화살표 키로 층 변경
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            e.preventDefault();
            const currentIndex = Array.from(this.floorButtons).findIndex(btn => 
                btn.classList.contains('active')
            );
            
            let nextIndex;
            if (e.key === 'ArrowUp') {
                nextIndex = currentIndex > 0 ? currentIndex - 1 : this.floorButtons.length - 1;
            } else {
                nextIndex = currentIndex < this.floorButtons.length - 1 ? currentIndex + 1 : 0;
            }
            
            if (this.floorButtons[nextIndex]) {
                this.floorButtons[nextIndex].click();
            }
        }
        
        // F5로 위치 강제 새로고침
        if (e.key === 'F5') {
            e.preventDefault();
            this.updateLocation();
            this.showMessage('위치 정보를 새로고침했습니다.', 'info');
        }
    }

    startLocationTracking() {
        // 즉시 한 번 실행
        this.updateLocation();
        
        // 주기적 업데이트 시작
        this.locationUpdateTimer = setInterval(() => {
            this.updateLocation();
        }, this.updateInterval);
    }

    stopLocationTracking() {
        if (this.locationUpdateTimer) {
            clearInterval(this.locationUpdateTimer);
            this.locationUpdateTimer = null;
        }
    }

    destroy() {
        this.stopLocationTracking();
        // 다른 정리 작업 수행
    }
}

// 페이지 언로드 시 정리
window.addEventListener('beforeunload', () => {
    if (window.dynamicMapSystem) {
        window.dynamicMapSystem.destroy();
    }
});

// 전역 객체로 설정
window.DynamicMapSystem = DynamicMapSystem;

// 자동 초기화 (지도가 있는 페이지에서만)
if (document.getElementById('map-container')) {
    window.dynamicMapSystem = new DynamicMapSystem();
}