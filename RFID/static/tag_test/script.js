// 최적화된 RFID 데이터 관리 시스템 (수정된 버전)
class RFIDManager {
    constructor() {
        this.cachedTags = [];
        this.isVisible = true;
        this.pollingInterval = null;
        this.currentPollingRate = 1000; // 기본 1초
        this.maxPollingRate = 5000; // 최대 5초
        this.noDataCount = 0;
        this.isPolling = false; // 중복 요청 방지
        
        this.initializeEventListeners();
        this.startOptimizedPolling();
    }

    // 이벤트 리스너 초기화
    initializeEventListeners() {
        // 페이지 가시성 변경 감지
        document.addEventListener('visibilitychange', () => {
            this.isVisible = !document.hidden;
            // console.log('페이지 가시성 변경:', this.isVisible ? '보임' : '숨김');
            
            if (this.isVisible) {
                this.resetPollingRate();
                this.checkRFIDData(); // 즉시 한 번 체크
            }
        });

        // 브라우저 포커스 감지
        window.addEventListener('focus', () => {
            this.isVisible = true;
            this.resetPollingRate();
            this.checkRFIDData();
        });

        window.addEventListener('blur', () => {
            this.isVisible = false;
        });
    }

    // 스마트 폴링 시작
    startOptimizedPolling() {
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        
        this.pollingInterval = setInterval(() => {
            if (this.isVisible && !this.isPolling) {
                this.checkRFIDData();
            }
        }, this.currentPollingRate);
        
        // console.log(`폴링 시작: ${this.currentPollingRate}ms 간격`);
    }

    // 폴링 주기 동적 조정
    adjustPollingRate(hasNewData) {
        const oldRate = this.currentPollingRate;
        
        if (hasNewData) {
            // 새 데이터가 있으면 폴링 주기를 빠르게
            this.currentPollingRate = 1000;
            this.noDataCount = 0;
            // console.log('새 데이터 감지: 폴링 주기를 1초로 조정');
        } else {
            // 새 데이터가 없으면 점진적으로 폴링 주기를 늘림
            this.noDataCount++;
            if (this.noDataCount > 5) { // 5번 연속 새 데이터 없음
                this.currentPollingRate = Math.min(
                    Math.floor(this.currentPollingRate * 1.2), 
                    this.maxPollingRate
                );
                // console.log(`폴링 주기 조정: ${oldRate}ms → ${this.currentPollingRate}ms (빈 응답 ${this.noDataCount}회)`);
            }
        }

        // 폴링 간격이 변경되었으면 재시작
        if (oldRate !== this.currentPollingRate) {
            this.startOptimizedPolling();
        }
    }

    // 폴링 주기 리셋
    resetPollingRate() {
        this.currentPollingRate = 1000;
        this.noDataCount = 0;
        this.startOptimizedPolling();
        // console.log('폴링 주기 리셋: 1초 간격으로 복원');
    }

    // RFID 데이터 확인 (수정된 버전 - since 파라미터 제거)
    async checkRFIDData() {
        if (this.isPolling) {
            // console.log('이미 폴링 중, 스킵');
            return;
        }

        this.isPolling = true;
        
        try {
            // since 파라미터 사용하지 않고 전체 데이터 요청
            const url = '/RFID/check_tag/';
            
            // console.log('RFID 데이터 요청:', url);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Cache-Control': 'no-cache',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            // console.log('받은 데이터:', data);
            
            // 새로운 데이터가 있는지 확인
            const hasNewData = data.tags && data.tags.length > 0;
            
            if (hasNewData) {
                // 기존 데이터와 비교하여 변경사항 확인
                const dataChanged = this.hasDataChanged(data.tags);
                
                if (dataChanged) {
                    // 전체 데이터로 교체
                    this.cachedTags = [...data.tags];
                    this.updateTagList(this.cachedTags);
                    
                    // 새 태그 시각적 피드백
                    this.notifyNewTags(data.tags);
                    
                    // console.log(`태그 목록 업데이트: ${data.tags.length}개`);
                } else {
                    // console.log('데이터 변경 없음');
                }
            } else {
                // 데이터가 없으면 캐시도 비우기
                if (this.cachedTags.length > 0) {
                    this.cachedTags = [];
                    this.updateTagList(this.cachedTags);
                    // console.log('모든 태그 제거됨');
                }
            }

            // 폴링 주기 조정
            this.adjustPollingRate(hasNewData);

        } catch (error) {
            console.error('RFID 데이터 확인 중 오류:', error);
            // 에러 발생 시 폴링 주기를 늘림
            this.adjustPollingRate(false);
        } finally {
            this.isPolling = false;
        }
    }

    // 데이터 변경 여부 확인
    hasDataChanged(newTags) {
        if (this.cachedTags.length !== newTags.length) {
            return true;
        }
        
        // page_id 기준으로 비교
        const cachedIds = new Set(this.cachedTags.map(tag => tag.page_id));
        const newIds = new Set(newTags.map(tag => tag.page_id));
        
        // Set의 크기가 다르거나, 새로운 ID가 있으면 변경됨
        if (cachedIds.size !== newIds.size) {
            return true;
        }
        
        for (let id of newIds) {
            if (!cachedIds.has(id)) {
                return true;
            }
        }
        
        return false;
    }

    // 새 태그 시각적 피드백
    notifyNewTags(newTags) {
        if (newTags.length > 0) {
            const tagList = document.getElementById('tag-list');
            if (tagList) {
                // 짧은 시각적 피드백
                tagList.style.transition = 'background-color 0.3s';
                tagList.style.backgroundColor = '#e8f5e8';
                setTimeout(() => {
                    tagList.style.backgroundColor = '';
                }, 500);
            }

            // 브라우저 알림 (권한이 있고 백그라운드인 경우)
            if (Notification.permission === 'granted' && !this.isVisible) {
                new Notification('새 RFID 태그 감지', {
                    body: `${newTags.length}개의 태그가 있습니다.`,
                    icon: '/static/favicon.ico',
                    tag: 'rfid-notification' // 중복 알림 방지
                });
            }
        }
    }

    // 태그 목록 업데이트 (최적화된 DOM 조작)
    updateTagList(tags) {
        const tagList = document.getElementById('tag-list');
        if (!tagList) {
            console.error('tag-list 요소를 찾을 수 없습니다');
            return;
        }

        // 태그가 없는 경우
        if (!tags || tags.length === 0) {
            tagList.innerHTML = '<div style="padding: 10px; color: #666; text-align: center;">최근 태그된 카드가 없습니다</div>';
            // console.log('태그 목록 비움');
            return;
        }

        // DocumentFragment 사용으로 DOM 조작 최적화
        const fragment = document.createDocumentFragment();
        
        tags.forEach((tag, index) => {
            const tagItem = document.createElement('div');
            tagItem.className = 'tag-item';
            tagItem.style.animationDelay = `${index * 0.05}s`; // 순차적 애니메이션
            
            // 만료 시간 정보가 있다면 표시
            const expireInfo = tag.expires_in_minutes !== undefined 
                ? `<div class="expire-info" style="font-size: 12px; color: #666;">만료까지: ${tag.expires_in_minutes}분</div>`
                : '';
            
            tagItem.innerHTML = `
                <div class="tag-code"><strong>RFID 코드:</strong> ${tag.code}</div>
                <div class="tag-time"><strong>시간:</strong> ${tag.time}</div>
                ${expireInfo}
            `;
            
            tagItem.onclick = () => {
                // console.log('태그 클릭:', tag.page_id);
                window.location.href = `/RFID/card_add/${tag.page_id}/`;
            };
            
            fragment.appendChild(tagItem);
        });

        // 한 번에 DOM 업데이트
        tagList.innerHTML = '';
        tagList.appendChild(fragment);
        
        // console.log(`태그 목록 업데이트 완료: ${tags.length}개 표시`);
    }

    // 알림 권한 요청
    async requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            try {
                const permission = await Notification.requestPermission();
                // console.log('알림 권한:', permission);
                return permission === 'granted';
            } catch (error) {
                // console.log('알림 권한 요청 실패:', error);
                return false;
            }
        }
        return Notification.permission === 'granted';
    }

    // 수동 새로고침
    forceRefresh() {
        // console.log('수동 새로고침 실행');
        this.cachedTags = []; // 캐시 완전 초기화
        this.resetPollingRate();
        this.checkRFIDData();
    }

    // 상태 정보 반환
    getStatus() {
        return {
            isVisible: this.isVisible,
            isPolling: this.isPolling,
            pollingRate: this.currentPollingRate,
            cachedCount: this.cachedTags.length,
            noDataCount: this.noDataCount
        };
    }

    // 정리 함수
    destroy() {
        // console.log('RFIDManager 정리 중...');
        if (this.pollingInterval) {
            clearInterval(this.pollingInterval);
        }
        this.isPolling = false;
    }
}

// 전역 인스턴스
let rfidManager;

// 페이지 로드 시 시작
document.addEventListener('DOMContentLoaded', async function() {
    // console.log('RFID 시스템 초기화 중...');
    
    rfidManager = new RFIDManager();
    
    // 알림 권한 요청 (선택사항)
    await rfidManager.requestNotificationPermission();
    
    // 수동 새로고침 버튼 이벤트 (있다면)
    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            rfidManager.forceRefresh();
        });
    }

    // 상태 확인 버튼 이벤트 (디버깅용, 있다면)
    const statusBtn = document.getElementById('status-btn');
    if (statusBtn) {
        statusBtn.addEventListener('click', () => {
            // console.log('현재 상태:', rfidManager.getStatus());
        });
    }

    // 페이지 언로드 시 정리
    window.addEventListener('beforeunload', () => {
        if (rfidManager) {
            rfidManager.destroy();
        }
    });

    // console.log('RFID 시스템 초기화 완료');
});

// 전역 함수들 (하위 호환성)
function checkRFIDData() {
    if (rfidManager) {
        rfidManager.forceRefresh();
    }
}

function updateTagList(tags) {
    if (rfidManager) {
        rfidManager.updateTagList(tags);
    }
}