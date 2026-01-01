/**
 * Common utilities for admin modules
 */

const TOKEN_KEY = 'admin_token';
const API_BASE_URL = '/api';

// Get college slug from window (set by Django template)
function getCollegeSlug() {
    return window.COLLEGE_SLUG || '';
}

// Build API endpoint with college slug
function buildApiEndpoint(endpoint) {
    const collegeSlug = getCollegeSlug();
    
    // Remove leading slash if present
    let cleanEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
    
    // Handle query strings - trailing slash should come before query string
    let baseEndpoint = cleanEndpoint;
    let queryString = '';
    
    if (cleanEndpoint.includes('?')) {
        const parts = cleanEndpoint.split('?');
        baseEndpoint = parts[0];
        queryString = '?' + parts[1];
    }
    
    // Add trailing slash if not present (Django requires it)
    // But preserve path parameters like /departments/123
    if (!baseEndpoint.endsWith('/')) {
        baseEndpoint = baseEndpoint + '/';
    }
    
    // Reconstruct endpoint with query string
    const finalEndpoint = baseEndpoint + queryString;
    
    if (collegeSlug) {
        return `/api/${collegeSlug}/${finalEndpoint}`;
    }
    // Fallback to regular API endpoint
    return `${API_BASE_URL}/${finalEndpoint}`;
}

// Token Management
function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function removeToken() {
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = '/admin/login/';
}

// Check authentication on page load
function checkAuth() {
    // For Django session-based auth, we rely on the server-side @login_required
    // If user is not authenticated, Django will redirect to login
    // So we don't need to check token here
    return true;
}

// API Call with authentication
async function apiCall(endpoint, options = {}) {
    // Get CSRF token for Django
    const csrftoken = window.csrftoken || getCookie('csrftoken');
    
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrftoken || '',
        },
        credentials: 'same-origin'  // Include session cookies
    };

    const config = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...(options.headers || {})
        }
    };

    try {
        const apiEndpoint = buildApiEndpoint(endpoint);
        const response = await fetch(apiEndpoint, config);
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            // If not JSON, might be HTML error page
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return null;
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
                // Redirect to login if unauthorized
                window.location.href = '/admin/login/';
                return null;
            }
            throw new Error(data.error || data.message || 'API request failed');
        }
        
        return data;
    } catch (error) {
        console.error('API Error:', error);
        showToast('error', error.message || 'An error occurred');
        throw error;
    }
}

// Helper to get CSRF token from cookies
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

// Toast notifications
function showToast(type, message, duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        info: 'fa-info-circle',
        warning: 'fa-exclamation-triangle'
    }[type] || 'fa-info-circle';
    
    toast.innerHTML = `
        <i class="fas ${icon}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideInRight 0.3s reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// Loading overlay
function showLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('hidden');
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('hidden');
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric' 
    });
}

// Format number
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// Modal helpers
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        const form = modal.querySelector('form');
        if (form) {
            form.reset();
            clearFormErrors(form);
        }
    }
}

function clearFormErrors(form) {
    if (!form) return;
    form.querySelectorAll('.error-message').forEach(el => {
        el.textContent = '';
        el.style.display = 'none';
    });
}

function showFieldError(fieldId, message) {
    const errorEl = document.getElementById(`error-${fieldId}`);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
}

// Pagination
function renderPagination(containerId, currentPage, totalPages, onPageChange) {
    const container = document.getElementById(containerId);
    if (!container) return;

    let html = '';
    
    // Previous button
    html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">
        <i class="fas fa-chevron-left"></i>
    </button>`;

    // Page numbers
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            html += `<span>...</span>`;
        }
    }

    // Next button
    html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">
        <i class="fas fa-chevron-right"></i>
    </button>`;

    container.innerHTML = html;

    // Attach event handlers
    window.goToPage = (page) => {
        if (page >= 1 && page <= totalPages) {
            onPageChange(page);
        }
    };
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
});

