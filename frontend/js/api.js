/**
 * Healthcare Appointment & Follow-up Manager - API Utility
 */

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000'
    : '';

const api = {
    /**
     * Base HTTP request wrapper using Fetch API
     */
    async request(endpoint, options = {}) {
        const url = `${API_BASE_URL}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {}),
        };

        // Attach JWT token if present in localStorage
        const token = localStorage.getItem('care_sync_token');
        if (token && !headers['Authorization']) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const config = {
            ...options,
            headers,
        };

        try {
            const response = await fetch(url, config);
            let data = null;

            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            if (!response.ok) {
                // If 401 and token was present, token is invalid/expired
                if (response.status === 401 && token) {
                    const isAuthPage = window.location.pathname.endsWith('login.html') || window.location.pathname.endsWith('register.html');
                    if (!isAuthPage) {
                        localStorage.removeItem('care_sync_token');
                        localStorage.removeItem('care_sync_user');
                        window.location.href = '/login.html';
                    }
                }

                const errorMsg = data && data.detail
                    ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
                    : `Request failed with status ${response.status}`;

                return {
                    success: false,
                    status: response.status,
                    error: errorMsg,
                    data,
                };
            }

            return {
                success: true,
                status: response.status,
                data,
            };
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            return {
                success: false,
                status: 0,
                error: error.message || 'Network error: Backend server unreachable',
                data: null,
            };
        }
    },

    get(endpoint, headers = {}) {
        return this.request(endpoint, { method: 'GET', headers });
    },

    post(endpoint, body = {}, headers = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(body),
            headers,
        });
    },

    put(endpoint, body = {}, headers = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(body),
            headers,
        });
    },

    delete(endpoint, headers = {}) {
        return this.request(endpoint, { method: 'DELETE', headers });
    },
};
