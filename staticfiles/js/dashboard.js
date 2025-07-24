// CCTV/static/cctv/js/dashboard.js

// API 기본 URL
const API_BASE_URL = '/CCTV/api/cameras/';

// 모달 관련 함수
function showAddCameraModal() {
    document.getElementById('modalTitle').textContent = '카메라 추가';
    document.getElementById('cameraForm').reset();
    document.getElementById('cameraId').value = '';
    document.getElementById('cameraModal').style.display = 'block';
}

function closeModal() {
    document.getElementById('cameraModal').style.display = 'none';
}

// 카메라 토글
async function toggleCamera(cameraId) {
    try {
        const response = await fetch(`${API_BASE_URL}${cameraId}/toggle_active/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });
        
        if (response.ok) {
            location.reload();
        } else {
            alert('카메라 상태 변경에 실패했습니다.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다.');
    }
}

// 카메라 수정
async function editCamera(cameraId) {
    try {
        const response = await fetch(`${API_BASE_URL}${cameraId}/`);
        const camera = await response.json();
        
        document.getElementById('modalTitle').textContent = '카메라 수정';
        document.getElementById('cameraId').value = camera.id;
        document.getElementById('name').value = camera.name;
        document.getElementById('api_key').value = camera.api_key;
        document.getElementById('workspace_name').value = camera.workspace_name;
        document.getElementById('workflow_id').value = camera.workflow_id;
        document.getElementById('rtsp_url').value = camera.rtsp_url;
        document.getElementById('max_fps').value = camera.max_fps;
        
        document.getElementById('cameraModal').style.display = 'block';
    } catch (error) {
        console.error('Error:', error);
        alert('카메라 정보를 불러올 수 없습니다.');
    }
}

// 카메라 삭제
async function deleteCamera(cameraId) {
    if (!confirm('정말로 이 카메라를 삭제하시겠습니까?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}${cameraId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        });
        
        if (response.ok) {
            location.reload();
        } else {
            alert('카메라 삭제에 실패했습니다.');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다.');
    }
}

// 폼 제출 처리
document.getElementById('cameraForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    const cameraId = data.id;
    delete data.id;
    
    try {
        const url = cameraId ? `${API_BASE_URL}${cameraId}/` : API_BASE_URL;
        const method = cameraId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify(data)
        });
        
        if (response.ok) {
            closeModal();
            location.reload();
        } else {
            const error = await response.json();
            alert('저장에 실패했습니다: ' + JSON.stringify(error));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다.');
    }
});

// CSRF 토큰 가져오기
function getCookie(name) {
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

// 모달 외부 클릭 시 닫기
window.onclick = function(event) {
    if (event.target == document.getElementById('cameraModal')) {
        closeModal();
    }
}