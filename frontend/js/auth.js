/**
 * Healthcare Appointment & Follow-up Manager - Authentication Module
 */

const TOKEN_KEY = 'care_sync_token';
const USER_KEY = 'care_sync_user';

const auth = {
    /**
     * Get stored JWT token
     */
    getToken() {
        return localStorage.getItem(TOKEN_KEY);
    },

    /**
     * Get stored user object
     */
    getUser() {
        const userStr = localStorage.getItem(USER_KEY);
        try {
            return userStr ? JSON.parse(userStr) : null;
        } catch {
            return null;
        }
    },

    /**
     * Check if user has active session
     */
    isAuthenticated() {
        return !!this.getToken();
    },

    /**
     * Resolve dashboard URL according to user role
     */
    getDashboardPath(role, prefix = '') {
        switch (role) {
            case 'PATIENT':
                return `${prefix}patient/dashboard.html`;
            case 'DOCTOR':
                return `${prefix}doctor/dashboard.html`;
            case 'ADMIN':
                return `${prefix}admin/dashboard.html`;
            default:
                return `${prefix}index.html`;
        }
    },

    /**
     * Authenticate user with email and password
     */
    async login(email, password) {
        const res = await api.post('/api/auth/login', { email, password });
        if (res.success && res.data) {
            localStorage.setItem(TOKEN_KEY, res.data.access_token);
            localStorage.setItem(USER_KEY, JSON.stringify(res.data.user));
            return {
                success: true,
                user: res.data.user,
                token: res.data.access_token,
            };
        }
        return {
            success: false,
            error: res.error || 'Login failed',
            status: res.status,
        };
    },

    /**
     * Register a new patient
     */
    async register(userData) {
        const res = await api.post('/api/auth/register', userData);
        if (res.success && res.data) {
            return {
                success: true,
                user: res.data,
            };
        }
        return {
            success: false,
            error: res.error || 'Registration failed',
            status: res.status,
        };
    },

    /**
     * Fetch current user profile from server
     */
    async getMe() {
        const res = await api.get('/api/auth/me');
        if (res.success && res.data) {
            localStorage.setItem(USER_KEY, JSON.stringify(res.data));
            return res.data;
        }
        return null;
    },

    /**
     * Log out current user and redirect
     */
    logout(redirectPath = 'login.html') {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        window.location.href = redirectPath;
    },

    /**
     * Protect page with authentication and role checking
     */
    async requireAuth(requiredRole = null, relativePrefix = '../') {
        const token = this.getToken();
        const user = this.getUser();

        if (!token || !user) {
            this.logout(`${relativePrefix}login.html`);
            return null;
        }

        // Verify token with backend
        const me = await this.getMe();
        if (!me) {
            this.logout(`${relativePrefix}login.html`);
            return null;
        }

        if (requiredRole && me.role !== requiredRole) {
            console.warn(`Role mismatch: required ${requiredRole}, got ${me.role}`);
            // Redirect to login with role switch hint
            window.location.href = `${relativePrefix}login.html?role=${encodeURIComponent(requiredRole.toLowerCase())}&switch=true&prevRole=${encodeURIComponent(me.role)}`;
            return null;
        }

        return me;
    },
};
