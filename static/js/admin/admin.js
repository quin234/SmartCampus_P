/**
 * SmartCampus Admin Portal - Main JavaScript
 * Handles authentication, API calls, and UI interactions
 */

// ============================================
// API Configuration
// ============================================

const API_BASE_URL = '/api/admin'; // Update with your actual API base URL
const TOKEN_KEY = 'admin_token';
const USER_KEY = 'admin_user';

// ============================================
// Utility Functions
// ============================================

/**
 * Get authentication token from localStorage
 */
function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

/**
 * Set authentication token in localStorage
 */
function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Remove authentication token from localStorage
 */
function removeToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
}

/**
 * Get user data from localStorage
 */
function getUser() {
    const userData = localStorage.getItem(USER_KEY);
    return userData ? JSON.parse(userData) : null;
}

/**
 * Set user data in localStorage
 */
function setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Make API call with authentication
 */
async function apiCall(endpoint, options = {}) {
    const token = getToken();
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` })
        }
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
        const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || 'API request failed');
        }
        
        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

/**
 * Show error message
 */
function showError(message, elementId = 'error-message') {
    const errorEl = document.getElementById(elementId);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
        setTimeout(() => {
            errorEl.style.display = 'none';
        }, 5000);
    }
}

/**
 * Show success message
 */
function showSuccess(message, elementId = 'success-message') {
    const successEl = document.getElementById(elementId);
    if (successEl) {
        successEl.textContent = message;
        successEl.style.display = 'block';
        setTimeout(() => {
            successEl.style.display = 'none';
        }, 3000);
    }
}

// ============================================
// Login Page Functionality
// ============================================

if (document.querySelector('.login-page')) {
    const loginForm = document.getElementById('login-form');
    const passwordToggle = document.getElementById('password-toggle');
    const passwordInput = document.getElementById('password');
    const loginBtn = document.getElementById('login-btn');

    // Password toggle functionality
    if (passwordToggle) {
        passwordToggle.addEventListener('click', () => {
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            
            const icon = passwordToggle.querySelector('i');
            icon.classList.toggle('fa-eye');
            icon.classList.toggle('fa-eye-slash');
        });
    }

    // Login form submission
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            // Don't prevent default - let form submit normally for Django
            // But add loading state
            
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;

            // Disable button and show loading
            loginBtn.disabled = true;
            loginBtn.querySelector('.btn-text').style.display = 'none';
            loginBtn.querySelector('.btn-loader').style.display = 'flex';

            // Store token for API calls (simulated - in production, get from response)
            const mockToken = 'session_token_' + Date.now();
            setToken(mockToken);
            setUser({ username, role: 'admin' });
            
            // Form will submit normally, Django will handle authentication
            // If login fails, page will reload with error
        });
    }
    
    // Check for error message on page load
    const errorMessage = document.querySelector('.error-message');
    if (errorMessage && errorMessage.textContent.trim()) {
        showError(errorMessage.textContent);
    }
}

/**
 * Get CSRF token from cookies
 */
function getCsrfToken() {
    const name = 'csrftoken';
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

// ============================================
// Dashboard Page Functionality
// ============================================

if (document.querySelector('.dashboard-page')) {
    // Check authentication on page load
    window.addEventListener('DOMContentLoaded', () => {
        checkAuthentication();
        initializeDashboard();
    });

    /**
     * Check if user is authenticated
     */
    function checkAuthentication() {
        // Check if we have a token (for API calls)
        // In production, verify token is valid via API call
        const token = getToken();
        
        // For now, rely on Django session authentication
        // If user is not authenticated, Django will redirect
        // But we can still check token for API calls
        
        // Load user data from localStorage or fetch from API
        const user = getUser();
        if (user) {
            updateUserDisplay(user);
        } else {
            // Try to fetch user data from API
            fetchUserData();
        }
    }
    
    /**
     * Fetch user data from API
     */
    async function fetchUserData() {
        try {
            // Placeholder API call - replace with actual endpoint
            // const userData = await apiCall('/user/profile');
            
            // For now, use mock data or get from page context
            const mockUser = {
                username: 'Admin',
                role: 'admin',
                college: 'SmartCampus College'
            };
            
            setUser(mockUser);
            updateUserDisplay(mockUser);
        } catch (error) {
            console.error('Error fetching user data:', error);
        }
    }

    /**
     * Update user display in navbar
     */
    function updateUserDisplay(user) {
        const profileName = document.getElementById('profile-name');
        const collegeName = document.getElementById('college-name');
        
        if (profileName) {
            profileName.textContent = user.username || 'Admin';
        }
        
        if (collegeName && user.college) {
            collegeName.textContent = user.college;
        }
    }

    /**
     * Initialize dashboard
     */
    function initializeDashboard() {
        setupMobileMenu();
        setupDropdowns();
        setupNavigation();
        loadDashboardData();
    }

    /**
     * Setup mobile menu toggle
     */
    function setupMobileMenu() {
        const mobileToggle = document.getElementById('mobile-menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebar-overlay');

        if (mobileToggle && sidebar) {
            mobileToggle.addEventListener('click', () => {
                sidebar.classList.toggle('active');
                if (overlay) {
                    overlay.classList.toggle('active');
                }
            });
        }

        if (overlay) {
            overlay.addEventListener('click', () => {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
            });
        }
    }

    /**
     * Setup dropdown menus
     */
    function setupDropdowns() {
        // Notification dropdown
        const notificationBtn = document.getElementById('notification-btn');
        const notificationMenu = document.getElementById('notification-menu');

        if (notificationBtn && notificationMenu) {
            notificationBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                notificationMenu.classList.toggle('active');
            });

            // Close on outside click
            document.addEventListener('click', (e) => {
                if (!notificationBtn.contains(e.target) && !notificationMenu.contains(e.target)) {
                    notificationMenu.classList.remove('active');
                }
            });
        }

        // Profile dropdown
        const profileBtn = document.getElementById('profile-btn');
        const profileMenu = document.getElementById('profile-menu');

        if (profileBtn && profileMenu) {
            profileBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                profileMenu.classList.toggle('active');
            });

            // Close on outside click
            document.addEventListener('click', (e) => {
                if (!profileBtn.contains(e.target) && !profileMenu.contains(e.target)) {
                    profileMenu.classList.remove('active');
                }
            });
        }
    }

    /**
     * Setup navigation links
     */
    function setupNavigation() {
        const navLinks = document.querySelectorAll('.nav-link[data-page]');
        
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.getAttribute('data-page');
                
                // Update active state
                document.querySelectorAll('.nav-item').forEach(item => {
                    item.classList.remove('active');
                });
                link.closest('.nav-item').classList.add('active');
                
                // Navigate to page (placeholder)
                console.log('Navigate to:', page);
                // In production: window.location.href = `/admin/${page}/`;
            });
        });
    }

    /**
     * Load dashboard data from API
     */
    async function loadDashboardData() {
        try {
            // Load overview statistics
            await loadOverviewStats();
            
            // Load announcements
            await loadAnnouncements();
            
            // Load system activity
            await loadSystemActivity();
            
        } catch (error) {
            console.error('Error loading dashboard data:', error);
        }
    }

    /**
     * Load overview statistics
     * Data is already loaded from backend via Django template
     * This function can be used for real-time updates via API
     */
    async function loadOverviewStats() {
        try {
            // Data is already rendered from backend
            // This can be used for periodic updates via API
            // const data = await apiCall('/dashboard/stats');
            
            // Format numbers that are already in the DOM
            document.querySelectorAll('.card-value').forEach(el => {
                const value = parseInt(el.textContent);
                if (!isNaN(value)) {
                    el.textContent = formatNumber(value);
                }
            });

        } catch (error) {
            console.error('Error loading overview stats:', error);
        }
    }

    /**
     * Load announcements
     * Data is already loaded from backend via Django template
     * This function can be used for real-time updates via API
     */
    async function loadAnnouncements() {
        try {
            // Data is already rendered from backend
            // This can be used for periodic updates via API
            // const data = await apiCall('/announcements/recent');
            console.log('Announcements loaded from backend');

        } catch (error) {
            console.error('Error loading announcements:', error);
        }
    }

    /**
     * Load system activity
     * Data is already loaded from backend via Django template
     * This function can be used for real-time updates via API
     */
    async function loadSystemActivity() {
        try {
            // Data is already rendered from backend
            // This can be used for periodic updates via API
            // const data = await apiCall('/activity/recent');
            console.log('System activity loaded from backend');

        } catch (error) {
            console.error('Error loading system activity:', error);
        }
    }

    /**
     * Format number with commas
     */
    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    /**
     * Logout functionality
     */
    function handleLogout() {
        // Clear token and user data from localStorage
        removeToken();
        
        // Get CSRF token
        const csrftoken = window.csrftoken || getCsrfToken();
        
        // Call Django logout endpoint to clear session
        fetch('/logout/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        }).then(() => {
            // Redirect to landing page
            window.location.href = '/';
        }).catch(() => {
            // If API call fails, still redirect
            window.location.href = '/';
        });
    }

    // Attach logout handlers
    const logoutBtns = document.querySelectorAll('#logout-btn, #sidebar-logout');
    logoutBtns.forEach(btn => {
        if (btn) {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                handleLogout();
            });
        }
    });
}

// ============================================
// Global Error Handler
// ============================================

window.addEventListener('error', (e) => {
    console.error('Global error:', e.error);
});

// ============================================
// Export functions for use in other scripts
// ============================================

window.AdminPortal = {
    getToken,
    setToken,
    removeToken,
    getUser,
    setUser,
    apiCall,
    showError,
    showSuccess
};

