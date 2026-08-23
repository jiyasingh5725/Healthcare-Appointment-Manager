/**
 * Healthcare Appointment & Follow-up Manager - Frontend Core JS & UI Helpers (Phase 21)
 */

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://127.0.0.1:8000'
    : '';

/**
 * Toast Notification System
 * @param {string} message - Text or HTML message
 * @param {'success'|'error'|'warning'|'info'} type - Toast variant
 * @param {number} duration - Milliseconds before self-dismiss
 */
function showToast(message, type = 'info', duration = 4000) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast-item';

    const icons = {
        success: '<div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-600 flex items-center justify-center flex-shrink-0 text-sm"><i class="fa-solid fa-circle-check"></i></div>',
        error: '<div class="w-8 h-8 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center flex-shrink-0 text-sm"><i class="fa-solid fa-circle-exclamation"></i></div>',
        warning: '<div class="w-8 h-8 rounded-xl bg-amber-100 text-amber-600 flex items-center justify-center flex-shrink-0 text-sm"><i class="fa-solid fa-triangle-exclamation"></i></div>',
        info: '<div class="w-8 h-8 rounded-xl bg-sky-100 text-sky-600 flex items-center justify-center flex-shrink-0 text-sm"><i class="fa-solid fa-circle-info"></i></div>'
    };

    toast.innerHTML = `
        ${icons[type] || icons.info}
        <div class="flex-1 text-xs">
            <p class="font-bold text-slate-900">${type.toUpperCase()}</p>
            <p class="text-slate-600 mt-0.5">${message}</p>
        </div>
        <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-slate-600 text-xs p-1">
            <i class="fa-solid fa-xmark"></i>
        </button>
    `;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 250);
    }, duration);
}

/**
 * Universal Confirmation Modal
 */
function showConfirmModal({ title, message, confirmText = 'Confirm', confirmStyle = 'bg-rose-600 hover:bg-rose-700', onConfirm }) {
    const existing = document.getElementById('global-confirm-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'global-confirm-modal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4 modal-backdrop';

    modal.innerHTML = `
        <div class="bg-white rounded-3xl max-w-md w-full p-6 sm:p-8 shadow-2xl border border-slate-200 modal-content-animated relative">
            <div class="w-12 h-12 rounded-2xl bg-slate-100 text-slate-700 flex items-center justify-center text-xl mb-4">
                <i class="fa-solid fa-circle-question text-sky-600"></i>
            </div>
            <h3 class="text-lg font-extrabold text-slate-900">${title}</h3>
            <p class="text-xs sm:text-sm text-slate-500 mt-2 leading-relaxed">${message}</p>
            
            <div class="mt-6 flex items-center justify-end space-x-3">
                <button id="modal-cancel-btn" class="px-4 py-2.5 text-xs font-bold text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-xl transition-all">
                    Cancel
                </button>
                <button id="modal-confirm-btn" class="px-5 py-2.5 text-xs font-bold text-white ${confirmStyle} rounded-xl shadow-md transition-all">
                    ${confirmText}
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    document.getElementById('modal-cancel-btn').addEventListener('click', () => modal.remove());
    document.getElementById('modal-confirm-btn').addEventListener('click', async () => {
        if (typeof onConfirm === 'function') {
            await onConfirm();
        }
        modal.remove();
    });
}

/**
 * Reusable Status Badges Renderer
 */
function getStatusBadge(status) {
    const normalized = (status || '').toUpperCase();
    switch (normalized) {
        case 'CONFIRMED':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>Confirmed</span>`;
        case 'COMPLETED':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-sky-50 text-sky-700 border border-sky-200"><i class="fa-solid fa-check-double mr-1.5 text-2xs"></i>Completed</span>`;
        case 'CANCELLED':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-rose-50 text-rose-700 border border-rose-200"><i class="fa-solid fa-ban mr-1.5 text-2xs"></i>Cancelled</span>`;
        case 'HOLD':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-amber-50 text-amber-700 border border-amber-200 animate-pulse"><i class="fa-solid fa-lock mr-1.5 text-2xs"></i>Held</span>`;
        case 'IN_PROGRESS':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200"><i class="fa-solid fa-stethoscope mr-1.5 text-2xs"></i>In Consultation</span>`;
        case 'ACTIVE':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>Active</span>`;
        case 'INACTIVE':
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-600 border border-slate-200"><span class="w-1.5 h-1.5 rounded-full bg-slate-400 mr-1.5"></span>Inactive</span>`;
        default:
            return `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700 border border-slate-200">${status}</span>`;
    }
}

/**
 * Check backend API health status
 */
async function checkApiHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('API Health check failed:', error);
        return { success: false, message: 'Backend unreachable' };
    }
}

/**
 * Check MySQL Database status
 */
async function checkDbStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/db-test`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('DB check failed:', error);
        return { success: false, message: 'DB unreachable' };
    }
}

// Global initialization on DOM ready
document.addEventListener('DOMContentLoaded', async () => {
    const healthIndicator = document.getElementById('api-status-badge');
    if (healthIndicator) {
        const health = await checkApiHealth();
        const db = await checkDbStatus();

        if (health && health.success && db && db.success) {
            healthIndicator.innerHTML = `
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200" title="API & DB Connected (${db.tables ? db.tables.length : 0} tables)">
                    <span class="w-2 h-2 mr-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                    API & DB Online
                </span>
            `;
        } else if (health && health.success) {
            healthIndicator.innerHTML = `
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-sky-100 text-sky-800 border border-sky-200">
                    <span class="w-2 h-2 mr-1.5 bg-sky-500 rounded-full"></span>
                    API Online (DB Pending)
                </span>
            `;
        } else {
            healthIndicator.innerHTML = `
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
                    <span class="w-2 h-2 mr-1.5 bg-amber-500 rounded-full"></span>
                    API Offline
                </span>
            `;
        }
    }
});
