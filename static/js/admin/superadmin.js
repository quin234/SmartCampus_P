/**
 * SmartCampus Super Admin Dashboard
 * Front-end JavaScript for Super Admin management interface
 */

// ============================================
// Configuration & Constants
// ============================================

const API_BASE_URL = '/api/superadmin';
const TOKEN_KEY = 'admin_token';
const USER_KEY = 'admin_user';

// ============================================
// Utility Functions
// ============================================

function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function removeToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    window.location.href = '/admin/login/';
}

function getUser() {
    const userData = localStorage.getItem(USER_KEY);
    return userData ? JSON.parse(userData) : null;
}

function setUser(user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
}

/**
 * Make API call with authentication
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 */
async function apiCall(endpoint, options = {}) {
    // Get CSRF token for Django session-based auth
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
        // Ensure endpoint starts with /
        const apiEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
        const response = await fetch(`${API_BASE_URL}${apiEndpoint}`, config);
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return null;
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            if (response.status === 401 || response.status === 403) {
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

/**
 * Show toast notification
 */
function showToast(type, message, duration = 3000) {
    const container = document.getElementById('toast-container');
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

/**
 * Show loading overlay
 */
function showLoading() {
    document.getElementById('loading-overlay').classList.remove('hidden');
}

/**
 * Hide loading overlay
 */
function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

/**
 * Format number with commas
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Format date
 */
function formatDate(dateString) {
    if (!dateString || dateString === '-') return '-';
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return dateString; // Return original if invalid
        return date.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
    } catch (e) {
        return dateString; // Return original string if parsing fails
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
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Skip token check for session-based authentication
    // Session-based auth doesn't use localStorage tokens
    // The Django session handles authentication
    
    // Initialize app
    initializeApp();
});

function initializeApp() {
    setupNavigation();
    setupModals();
    setupForms();
    setupTables();
    setupCollegesCardsModal();
    setupCollegeDetailModal();
    setupClickableCards();
    setupDetailModal();
    
    // Only load dashboard data if we're on the dashboard page
    if (document.getElementById('total-colleges') || window.location.pathname.includes('/dashboard')) {
        loadDashboardData();
    }
    
    loadUserProfile();
}

// ============================================
// Navigation
// ============================================

function setupNavigation() {
    // Sidebar toggle
    const sidebarToggle = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('active');
        });
    }

    // Navigation items - set active state based on current URL
    const navItems = document.querySelectorAll('.nav-item[data-page]');
    const currentPath = window.location.pathname;
    
    navItems.forEach(item => {
        const navLink = item.querySelector('.nav-link');
        if (navLink) {
            const href = navLink.getAttribute('href');
            // Set active state based on current URL
            if (href && (currentPath === href || currentPath.startsWith(href + '/'))) {
                navItems.forEach(ni => ni.classList.remove('active'));
                item.classList.add('active');
            }
            
            // Only add event listeners for single-page app links (no real href)
            if (!href || href === '#' || href.startsWith('javascript:')) {
                // Single-page app link - prevent default and use showPage
                navLink.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const page = item.getAttribute('data-page');
                    if (typeof showPage === 'function') {
                        showPage(page);
                    }
                    navItems.forEach(ni => ni.classList.remove('active'));
                    item.classList.add('active');
                });
            }
            // For real links with href, NO event listener is added
            // They will work naturally via browser navigation
        }
    });

    // Profile dropdown
    const profileBtn = document.getElementById('profile-btn');
    const profileMenu = document.getElementById('profile-menu');
    
    if (profileBtn && profileMenu) {
        profileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            profileMenu.classList.toggle('active');
        });

        document.addEventListener('click', (e) => {
            if (!profileBtn.contains(e.target) && !profileMenu.contains(e.target)) {
                profileMenu.classList.remove('active');
            }
        });
    }

    // Dropdown actions
    const dropdownItems = document.querySelectorAll('.dropdown-item[data-action]');
    dropdownItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const action = item.getAttribute('data-action');
            handleDropdownAction(action);
        });
    });

    // Logout - handle both direct links and JavaScript handlers
    const logoutBtns = document.querySelectorAll('#sidebar-logout, .dropdown-item[data-action="logout"]');
    logoutBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            handleLogout();
        });
    });

    // FAB button
    const fabBtn = document.getElementById('fab-add-college');
    if (fabBtn) {
        fabBtn.addEventListener('click', () => {
            openCollegeModal();
        });
    }

    // View all colleges button
    const viewAllBtn = document.getElementById('view-all-colleges');
    if (viewAllBtn) {
        viewAllBtn.addEventListener('click', () => {
            showPage('colleges');
            document.querySelector('.nav-item[data-page="colleges"]').classList.add('active');
            document.querySelector('.nav-item[data-page="dashboard"]').classList.remove('active');
        });
    }
}

function showPage(pageName) {
    // Hide all pages
    document.querySelectorAll('.page-content').forEach(page => {
        page.classList.add('hidden');
    });

    // Show selected page
    const page = document.getElementById(`page-${pageName}`);
    if (page) {
        page.classList.remove('hidden');
        
        // Load page-specific data
        if (pageName === 'colleges') {
            loadColleges();
        } else if (pageName === 'analytics') {
            loadAnalytics();
        } else if (pageName === 'settings') {
            loadSettings();
        } else if (pageName === 'profile') {
            loadProfile();
        }
    }
}

function handleDropdownAction(action) {
    switch(action) {
        case 'profile':
            showPage('profile');
            break;
        case 'settings':
            showPage('settings');
            break;
        case 'logout':
            handleLogout();
            break;
    }
}

function handleLogout() {
    if (confirm('Are you sure you want to logout?')) {
        // Clear token and user data from localStorage
        removeToken();
        
        // Get CSRF token
        const csrftoken = window.csrftoken || getCsrfToken();
        
        // Call Django logout endpoint to clear session
        fetch('/superadmin/logout/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin'
        }).then(() => {
            // Redirect to admin login (as per requirements)
            window.location.href = '/admin/login/';
        }).catch(() => {
            // If API call fails, still redirect
            window.location.href = '/admin/login/';
        });
    }
}

// ============================================
// Dashboard Data Loading
// ============================================

async function loadDashboardData() {
    // Only run on dashboard page - check if dashboard elements exist
    if (!document.getElementById('total-colleges') && !window.location.pathname.includes('/dashboard')) {
        return; // Not on dashboard page, exit early
    }
    
    showLoading();
    try {
        // Load overview statistics
        // API: GET /api/superadmin/overview
        const overview = await apiCall('/overview');
        
        if (overview) {
            updateAnalyticsCards(overview);
            // Only update these if elements exist (dashboard page only)
            const recentTbody = document.getElementById('recent-colleges-tbody');
            if (recentTbody) {
                updateRecentColleges(overview.recent_colleges || []);
            }
            // Only initialize charts if chart containers exist
            if (typeof initializeCharts === 'function' && document.querySelector('.chart-container')) {
                initializeCharts(overview);
            }
        } else {
            // Mock data for demonstration
            const mockData = {
                total_colleges: 25,
                total_students: 12500,
                total_lecturers: 450,
                total_departments: 120,
                active_colleges: 22,
                suspended_colleges: 3,
                colleges_change: 3,
                recent_colleges: [],
                growth_data: [],
                distribution_data: []
            };
            updateAnalyticsCards(mockData);
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    } finally {
        hideLoading();
    }
}

function updateAnalyticsCards(data) {
    // Safely update elements only if they exist (dashboard page only)
    // Exit early if we're not on the dashboard page
    if (!document.getElementById('total-colleges') && !window.location.pathname.includes('/dashboard')) {
        return; // Not on dashboard page, exit early
    }
    
    const elements = {
        'total-colleges': formatNumber(data.total_colleges || 0),
        'total-students': formatNumber(data.total_students || 0),
        'total-lecturers': formatNumber(data.total_lecturers || 0),
        'total-departments': formatNumber(data.total_departments || 0),
        'active-colleges': formatNumber(data.active_colleges || 0),
        'suspended-colleges': formatNumber(data.suspended_colleges || 0),
        'colleges-change': `${data.colleges_change || 0} this month`
    };
    
    for (const [id, value] of Object.entries(elements)) {
        const element = document.getElementById(id);
        if (element && element.textContent !== undefined) {
            try {
                element.textContent = value;
            } catch (e) {
                console.warn(`Could not update element ${id}:`, e);
            }
        }
    }
}

function updateRecentColleges(colleges) {
    const tbody = document.getElementById('recent-colleges-tbody');
    if (!tbody) return;

    if (colleges.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="loading-row">No recent registrations</td></tr>';
        return;
    }

    tbody.innerHTML = colleges.map(college => `
        <tr>
            <td>${college.name}</td>
            <td>${college.principal_name || '-'}</td>
            <td>${college.email}</td>
            <td>${college.county || '-'}</td>
            <td>${formatDate(college.created_at)}</td>
            <td><span class="badge badge-${college.registration_status}">${college.registration_status}</span></td>
            <td>
                <button class="btn btn-sm btn-primary" onclick="viewCollege(${college.id})">View</button>
            </td>
        </tr>
    `).join('');
}

// ============================================
// Charts
// ============================================

let growthChart = null;
let distributionChart = null;

function initializeCharts(data) {
    // Colleges Growth Chart
    const growthCtx = document.getElementById('colleges-growth-chart');
    if (growthCtx) {
        // Destroy existing chart if it exists
        if (growthChart) {
            growthChart.destroy();
            growthChart = null;
        }
        // Also check if Chart.js has a chart instance on this canvas
        const existingChart = Chart.getChart(growthCtx);
        if (existingChart) {
            existingChart.destroy();
        }
        
        const growthData = data.growth_data || generateMockGrowthData();
        
        growthChart = new Chart(growthCtx, {
            type: 'bar',
            data: {
                labels: growthData.labels,
                datasets: [{
                    label: 'New Colleges',
                    data: growthData.values,
                    backgroundColor: 'rgba(37, 99, 235, 0.8)',
                    borderColor: 'rgba(37, 99, 235, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    }

    // Student Distribution Chart
    const distCtx = document.getElementById('student-distribution-chart');
    if (distCtx) {
        // Destroy existing chart if it exists
        if (distributionChart) {
            distributionChart.destroy();
            distributionChart = null;
        }
        // Also check if Chart.js has a chart instance on this canvas
        const existingChart = Chart.getChart(distCtx);
        if (existingChart) {
            existingChart.destroy();
        }
        
        const distData = data.distribution_data || generateMockDistributionData();
        
        distributionChart = new Chart(distCtx, {
            type: 'doughnut',
            data: {
                labels: distData.labels,
                datasets: [{
                    data: distData.values,
                    backgroundColor: [
                        'rgba(37, 99, 235, 0.8)',
                        'rgba(16, 185, 129, 0.8)',
                        'rgba(245, 158, 11, 0.8)',
                        'rgba(239, 68, 68, 0.8)',
                        'rgba(139, 92, 246, 0.8)'
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
}

function generateMockGrowthData() {
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
    return {
        labels: months,
        values: [2, 3, 5, 4, 6, 5]
    };
}

function generateMockDistributionData() {
    return {
        labels: ['Small (0-100)', 'Medium (101-500)', 'Large (501-1000)', 'Very Large (1000+)'],
        values: [5, 12, 6, 2]
    };
}

// ============================================
// Colleges Management
// ============================================

let collegesData = [];
let currentPage = 1;
const itemsPerPage = 10;

async function loadColleges() {
    showLoading();
    try {
        // API: GET /api/superadmin/colleges?page=1&status=&type=&search=
        const params = new URLSearchParams({
            page: currentPage,
            status: document.getElementById('status-filter')?.value || '',
            type: document.getElementById('type-filter')?.value || '',
            search: document.getElementById('college-search')?.value || ''
        });

        const data = await apiCall(`/colleges/?${params}`);
        
        if (data && data.results) {
            // Map API field names to expected names
            collegesData = data.results.map(college => ({
                id: college.id,
                name: college.name,
                principal_name: college.owner || college.principal_name || '-',
                email: college.email || '-',
                phone: college.phone || '-',
                county: college.location || college.county || '-',
                type: college.type || '-',
                created_at: college.date_registered || college.created_at || '-',
                registration_status: college.status || college.registration_status || 'pending',
                address: college.address || '',
                status_display: college.status_display || college.status || 'pending'
            }));
            renderCollegesTable(collegesData);
            renderPagination(data.total_pages || 1);
        } else {
            // Handle empty results
            collegesData = [];
            renderCollegesTable([]);
            renderPagination(1);
        }
    } catch (error) {
        console.error('Error loading colleges:', error);
        showToast('error', 'Failed to load colleges');
        collegesData = [];
        renderCollegesTable([]);
    } finally {
        hideLoading();
    }
}

function generateMockColleges() {
    return [
        {
            id: 1,
            name: 'Nairobi Technical College',
            principal_name: 'Dr. John Doe',
            email: 'info@nairobi-tech.ac.ke',
            phone: '+254 700 000 000',
            county: 'Nairobi',
            type: 'TVET',
            created_at: '2024-01-15',
            registration_status: 'active'
        },
        {
            id: 2,
            name: 'Mombasa University',
            principal_name: 'Prof. Jane Smith',
            email: 'admin@mombasa-university.ac.ke',
            phone: '+254 700 000 001',
            county: 'Mombasa',
            type: 'University',
            created_at: '2024-02-20',
            registration_status: 'pending'
        }
    ];
}

function renderCollegesTable(colleges) {
    const tbody = document.getElementById('colleges-tbody');
    if (!tbody) return;

    if (colleges.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="loading-row">No colleges found</td></tr>';
        return;
    }

    tbody.innerHTML = colleges.map(college => `
        <tr>
            <td>
                <input type="checkbox" class="college-checkbox" value="${college.id}">
            </td>
            <td>${college.name || '-'}</td>
            <td>${college.principal_name || '-'}</td>
            <td>${college.email || '-'}</td>
            <td>${college.phone || '-'}</td>
            <td>${college.county || '-'}</td>
            <td>${college.type || '-'}</td>
            <td>${college.created_at ? formatDate(college.created_at) : '-'}</td>
            <td>
                <span class="badge badge-${college.registration_status || 'pending'}">${college.status_display || college.registration_status || 'pending'}</span>
            </td>
            <td>
                <div class="action-buttons">
                    ${college.registration_status === 'pending' ? `
                    <button class="btn btn-sm btn-success" onclick="approveCollege(${college.id})" title="Approve">
                        <i class="fas fa-check"></i>
                    </button>
                    ` : ''}
                    ${college.registration_status === 'active' ? `
                    <button class="btn btn-sm btn-warning" onclick="suspendCollege(${college.id})" title="Suspend">
                        <i class="fas fa-ban"></i>
                    </button>
                    ` : ''}
                    <button class="btn btn-sm btn-primary" onclick="editCollege(${college.id})" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteCollege(${college.id})" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');

    setupCheckboxes();
}

function renderPagination(totalPages) {
    const pagination = document.getElementById('colleges-pagination');
    if (!pagination) return;

    let html = '';
    for (let i = 1; i <= totalPages; i++) {
        html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
    }
    pagination.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    loadColleges();
}

function setupCheckboxes() {
    const selectAll = document.getElementById('select-all');
    const checkboxes = document.querySelectorAll('.college-checkbox');
    const bulkActions = document.getElementById('bulk-actions');
    const selectedCount = document.getElementById('selected-count');

    if (selectAll) {
        selectAll.addEventListener('change', (e) => {
            checkboxes.forEach(cb => cb.checked = e.target.checked);
            updateBulkActions();
        });
    }

    checkboxes.forEach(cb => {
        cb.addEventListener('change', updateBulkActions);
    });

    function updateBulkActions() {
        const selected = Array.from(checkboxes).filter(cb => cb.checked);
        if (selected.length > 0) {
            bulkActions.classList.remove('hidden');
            selectedCount.textContent = `${selected.length} selected`;
        } else {
            bulkActions.classList.add('hidden');
        }
    }
}

// ============================================
// College Actions
// ============================================

async function approveCollege(id) {
    if (!confirm('Approve this college?')) return;
    
    showLoading();
    try {
        // API: PUT /api/colleges/:id/approve
        await apiCall(`/colleges/${id}/approve/`, { method: 'PUT' });
        showToast('success', 'College approved successfully');
        loadColleges();
        loadDashboardData();
    } catch (error) {
        console.error('Error approving college:', error);
    } finally {
        hideLoading();
    }
}

async function suspendCollege(id) {
    if (!confirm('Suspend this college?')) return;
    
    showLoading();
    try {
        // API: PUT /api/colleges/:id/suspend
        await apiCall(`/colleges/${id}/suspend/`, { method: 'PUT' });
        showToast('success', 'College suspended successfully');
        loadColleges();
        loadDashboardData();
    } catch (error) {
        console.error('Error suspending college:', error);
    } finally {
        hideLoading();
    }
}

async function editCollege(id) {
    const college = collegesData.find(c => c.id === id);
    if (!college) return;
    
    openCollegeModal(college);
}

async function deleteCollege(id) {
    if (!confirm('Are you sure you want to delete this college? This action cannot be undone.')) return;
    
    showLoading();
    try {
        // API: DELETE /api/colleges/:id
        await apiCall(`/colleges/${id}/`, { method: 'DELETE' });
        showToast('success', 'College deleted successfully');
        loadColleges();
        loadDashboardData();
    } catch (error) {
        console.error('Error deleting college:', error);
    } finally {
        hideLoading();
    }
}

function viewCollege(id) {
    // Navigate to college detail page or show modal
    showPage('colleges');
    // Could implement a detail view here
}

// ============================================
// Modals
// ============================================

function setupModals() {
    const modal = document.getElementById('college-modal');
    const closeBtn = document.getElementById('modal-close');
    const cancelBtn = document.getElementById('modal-cancel');
    const denyModal = document.getElementById('deny-modal');
    const denyClose = document.getElementById('deny-modal-close');
    const denyCancel = document.getElementById('deny-cancel');

    // Close modal on background click
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeModal();
            }
        });
    }

    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
    if (denyClose) denyClose.addEventListener('click', () => denyModal.classList.remove('active'));
    if (denyCancel) denyCancel.addEventListener('click', () => denyModal.classList.remove('active'));
}

function openCollegeModal(college = null) {
    const modal = document.getElementById('college-modal');
    const form = document.getElementById('college-form');
    const title = document.getElementById('modal-title');
    
    if (college) {
        title.textContent = 'Edit College';
        // Prefill form
        document.getElementById('college-name').value = college.name || '';
        document.getElementById('owner-name').value = college.principal_name || '';
        document.getElementById('owner-email').value = college.email || '';
        document.getElementById('owner-phone').value = college.phone || '';
        document.getElementById('location').value = college.county || '';
        document.getElementById('college-type').value = college.type || '';
        document.getElementById('address').value = college.address || '';
        document.getElementById('website').value = college.website || '';
        document.getElementById('college-status').value = college.registration_status || 'pending';
        form.dataset.collegeId = college.id;
    } else {
        title.textContent = 'Add New College';
        form.reset();
        delete form.dataset.collegeId;
    }
    
    modal.classList.add('active');
}

function closeModal() {
    const modal = document.getElementById('college-modal');
    const form = document.getElementById('college-form');
    modal.classList.remove('active');
    form.reset();
    clearFormErrors();
}

function clearFormErrors() {
    document.querySelectorAll('.error-message').forEach(el => {
        el.textContent = '';
    });
}

// ============================================
// Forms
// ============================================

function setupForms() {
    // College form
    const collegeForm = document.getElementById('college-form');
    if (collegeForm) {
        collegeForm.addEventListener('submit', handleCollegeSubmit);
    }

    // Settings form
    const settingsForm = document.getElementById('settings-form');
    if (settingsForm) {
        settingsForm.addEventListener('submit', handleSettingsSubmit);
    }

    // Profile form
    const profileForm = document.getElementById('profile-form');
    if (profileForm) {
        profileForm.addEventListener('submit', handleProfileSubmit);
    }

    // Deny form
    const denyForm = document.getElementById('deny-form');
    if (denyForm) {
        denyForm.addEventListener('submit', handleDenySubmit);
    }

    // Search and filters
    const searchInput = document.getElementById('college-search');
    const statusFilter = document.getElementById('status-filter');
    const typeFilter = document.getElementById('type-filter');
    const clearFilters = document.getElementById('clear-filters');

    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                currentPage = 1;
                loadColleges();
            }, 500);
        });
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', () => {
            currentPage = 1;
            loadColleges();
        });
    }

    if (typeFilter) {
        typeFilter.addEventListener('change', () => {
            currentPage = 1;
            loadColleges();
        });
    }

    if (clearFilters) {
        clearFilters.addEventListener('click', () => {
            document.getElementById('college-search').value = '';
            document.getElementById('status-filter').value = '';
            document.getElementById('type-filter').value = '';
            document.getElementById('date-from').value = '';
            document.getElementById('date-to').value = '';
            currentPage = 1;
            loadColleges();
        });
    }

    // Bulk actions
    document.getElementById('bulk-approve')?.addEventListener('click', handleBulkApprove);
    document.getElementById('bulk-suspend')?.addEventListener('click', handleBulkSuspend);
    document.getElementById('bulk-delete')?.addEventListener('click', handleBulkDelete);
}

async function handleCollegeSubmit(e) {
    e.preventDefault();
    const form = e.target;
    const submitBtn = document.getElementById('modal-submit');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoader = submitBtn.querySelector('.btn-loader');
    
    clearFormErrors();
    
    const formData = {
        name: document.getElementById('college-name').value,
        owner_name: document.getElementById('owner-name').value,
        owner_email: document.getElementById('owner-email').value,
        owner_phone: document.getElementById('owner-phone').value,
        location: document.getElementById('location').value,
        type: document.getElementById('college-type').value,
        address: document.getElementById('address').value,
        website: document.getElementById('website').value,
        status: document.getElementById('college-status').value
    };

    // Validation
    if (!validateCollegeForm(formData)) {
        return;
    }

    btnText.style.display = 'none';
    btnLoader.classList.remove('hidden');
    submitBtn.disabled = true;

    try {
        const collegeId = form.dataset.collegeId;
        let response;
        
        if (collegeId) {
            // API: PUT /api/colleges/:id
            response = await apiCall(`/colleges/${collegeId}/`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
        } else {
            // API: POST /api/colleges
            response = await apiCall('/colleges/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
        }

        if (response) {
            showToast('success', collegeId ? 'College updated successfully' : 'College created successfully');
            closeModal();
            loadColleges();
            loadDashboardData();
        }
    } catch (error) {
        console.error('Error saving college:', error);
    } finally {
        btnText.style.display = 'inline';
        btnLoader.classList.add('hidden');
        submitBtn.disabled = false;
    }
}

function validateCollegeForm(data) {
    let isValid = true;
    
    if (!data.name.trim()) {
        showFieldError('college-name', 'College name is required');
        isValid = false;
    }
    if (!data.owner_name.trim()) {
        showFieldError('owner-name', 'Owner/Principal name is required');
        isValid = false;
    }
    if (!data.owner_email.trim() || !isValidEmail(data.owner_email)) {
        showFieldError('owner-email', 'Valid email is required');
        isValid = false;
    }
    if (!data.owner_phone.trim()) {
        showFieldError('owner-phone', 'Phone number is required');
        isValid = false;
    }
    if (!data.location.trim()) {
        showFieldError('location', 'Location is required');
        isValid = false;
    }
    if (!data.type) {
        showFieldError('college-type', 'College type is required');
        isValid = false;
    }
    
    return isValid;
}

function showFieldError(fieldId, message) {
    const errorEl = document.getElementById(`error-${fieldId}`);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

async function handleSettingsSubmit(e) {
    e.preventDefault();
    showLoading();
    
    const settings = {
        platform_name: document.getElementById('platform-name').value,
        default_status: document.getElementById('default-status').value,
        system_email: document.getElementById('system-email').value
    };

    try {
        // API: PUT /api/superadmin/settings
        await apiCall('/settings', {
            method: 'PUT',
            body: JSON.stringify(settings)
        });
        showToast('success', 'Settings saved successfully');
    } catch (error) {
        console.error('Error saving settings:', error);
    } finally {
        hideLoading();
    }
}

async function handleProfileSubmit(e) {
    e.preventDefault();
    showLoading();
    
    const profile = {
        name: document.getElementById('profile-name').value,
        email: document.getElementById('profile-email').value,
        phone: document.getElementById('profile-phone').value
    };

    try {
        // API: PUT /api/superadmin/profile
        await apiCall('/profile', {
            method: 'PUT',
            body: JSON.stringify(profile)
        });
        showToast('success', 'Profile updated successfully');
        loadUserProfile();
    } catch (error) {
        console.error('Error updating profile:', error);
    } finally {
        hideLoading();
    }
}

function handleDenySubmit(e) {
    e.preventDefault();
    const reason = document.getElementById('deny-reason').value;
    // Handle denial logic
    showToast('info', 'Registration denied');
    document.getElementById('deny-modal').classList.remove('active');
}

// ============================================
// Bulk Actions
// ============================================

async function handleBulkApprove() {
    const selected = getSelectedColleges();
    if (selected.length === 0) return;
    
    if (!confirm(`Approve ${selected.length} selected college(s)?`)) return;
    
    showLoading();
    try {
        // API: PUT /api/colleges/bulk-approve
        await apiCall('/colleges/bulk-approve/', {
            method: 'PUT',
            body: JSON.stringify({ ids: selected })
        });
        showToast('success', `${selected.length} college(s) approved`);
        loadColleges();
        loadDashboardData();
    } catch (error) {
        console.error('Error bulk approving:', error);
    } finally {
        hideLoading();
    }
}

async function handleBulkSuspend() {
    const selected = getSelectedColleges();
    if (selected.length === 0) return;
    
    if (!confirm(`Suspend ${selected.length} selected college(s)?`)) return;
    
    showLoading();
    try {
        // API: PUT /api/colleges/bulk-suspend
        await apiCall('/colleges/bulk-suspend/', {
            method: 'PUT',
            body: JSON.stringify({ ids: selected })
        });
        showToast('success', `${selected.length} college(s) suspended`);
        loadColleges();
        loadDashboardData();
    } catch (error) {
        console.error('Error bulk suspending:', error);
    } finally {
        hideLoading();
    }
}

async function handleBulkDelete() {
    const selected = getSelectedColleges();
    if (selected.length === 0) return;
    
    if (!confirm(`Delete ${selected.length} selected college(s)? This action cannot be undone.`)) return;
    
    showLoading();
    try {
        // API: DELETE /api/colleges/bulk-delete
        await apiCall('/colleges/bulk-delete/', {
            method: 'DELETE',
            body: JSON.stringify({ ids: selected })
        });
        showToast('success', `${selected.length} college(s) deleted`);
        loadColleges();
        loadDashboardData();
    } catch (error) {
        console.error('Error bulk deleting:', error);
    } finally {
        hideLoading();
    }
}

function getSelectedColleges() {
    return Array.from(document.querySelectorAll('.college-checkbox:checked'))
        .map(cb => parseInt(cb.value));
}

// ============================================
// Data Loading Functions
// ============================================

async function loadAnalytics() {
    showLoading();
    try {
        // API: GET /api/superadmin/analytics
        const data = await apiCall('/analytics');
        
        if (data) {
            updateAnalyticsOverviewCards(data.overview);
            renderAnalyticsCharts(data);
            populateTopCollegesTable(data.top_colleges);
            populateRecentRegistrationsTable(data.recent_registrations);
        } else {
            showToast('error', 'Failed to load analytics data');
        }
    } catch (error) {
        console.error('Error loading analytics:', error);
        showToast('error', 'Failed to load analytics data');
    } finally {
        hideLoading();
    }
}

function updateAnalyticsOverviewCards(overview) {
    if (!overview) return;
    
    const totalCollegesEl = document.getElementById('dashboard-analytics-total-colleges');
    const totalStudentsEl = document.getElementById('dashboard-analytics-total-students');
    const totalLecturersEl = document.getElementById('dashboard-analytics-total-lecturers');
    const totalCoursesEl = document.getElementById('dashboard-analytics-total-courses');
    
    if (totalCollegesEl) totalCollegesEl.textContent = overview.total_colleges || 0;
    if (totalStudentsEl) totalStudentsEl.textContent = overview.total_students || 0;
    if (totalLecturersEl) totalLecturersEl.textContent = overview.total_lecturers || 0;
    if (totalCoursesEl) totalCoursesEl.textContent = overview.total_courses || 0;
}

function renderAnalyticsCharts(data) {
    if (!data) return;
    
    // Colleges Growth Chart
    const collegesGrowthCtx = document.getElementById('dashboard-colleges-growth-chart');
    if (collegesGrowthCtx && data.growth_trends && data.growth_trends.colleges) {
        // Destroy existing chart if it exists
        if (window.collegesGrowthChart) {
            window.collegesGrowthChart.destroy();
            window.collegesGrowthChart = null;
        }
        // Also check if Chart.js has a chart instance on this canvas
        const existingChart = Chart.getChart(collegesGrowthCtx);
        if (existingChart) {
            existingChart.destroy();
        }
        
        window.collegesGrowthChart = new Chart(collegesGrowthCtx, {
            type: 'line',
            data: {
                labels: data.growth_trends.colleges.map(item => item.month),
                datasets: [{
                    label: 'Colleges',
                    data: data.growth_trends.colleges.map(item => item.count),
                    borderColor: '#1e40af',
                    backgroundColor: 'rgba(30, 64, 175, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    // Student Distribution Chart
    const studentDistCtx = document.getElementById('dashboard-student-distribution-chart');
    if (studentDistCtx && data.distributions && data.distributions.students_by_college) {
        if (window.studentDistChart) {
            window.studentDistChart.destroy();
            window.studentDistChart = null;
        }
        // Also check if Chart.js has a chart instance on this canvas
        const existingChart = Chart.getChart(studentDistCtx);
        if (existingChart) {
            existingChart.destroy();
        }
        
        window.studentDistChart = new Chart(studentDistCtx, {
            type: 'bar',
            data: {
                labels: data.distributions.students_by_college.map(item => item.college),
                datasets: [{
                    label: 'Students',
                    data: data.distributions.students_by_college.map(item => item.students),
                    backgroundColor: '#3b82f6'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }

    // Status Distribution Chart
    const statusDistCtx = document.getElementById('dashboard-status-distribution-chart');
    if (statusDistCtx && data.status_breakdown) {
        if (window.statusDistChart) {
            window.statusDistChart.destroy();
            window.statusDistChart = null;
        }
        // Also check if Chart.js has a chart instance on this canvas
        const existingChart = Chart.getChart(statusDistCtx);
        if (existingChart) {
            existingChart.destroy();
        }
        
        window.statusDistChart = new Chart(statusDistCtx, {
            type: 'pie',
            data: {
                labels: ['Active', 'Pending', 'Inactive'],
                datasets: [{
                    data: [
                        data.status_breakdown.active || 0,
                        data.status_breakdown.pending || 0,
                        data.status_breakdown.inactive || 0
                    ],
                    backgroundColor: ['#10b981', '#f59e0b', '#ef4444']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    // Lecturers by College Chart
    const lecturersCtx = document.getElementById('dashboard-lecturers-by-college-chart');
    if (lecturersCtx && data.distributions && data.distributions.lecturers_by_college) {
        if (window.lecturersChart) {
            window.lecturersChart.destroy();
            window.lecturersChart = null;
        }
        // Also check if Chart.js has a chart instance on this canvas
        const existingChart = Chart.getChart(lecturersCtx);
        if (existingChart) {
            existingChart.destroy();
        }
        
        window.lecturersChart = new Chart(lecturersCtx, {
            type: 'bar',
            data: {
                labels: data.distributions.lecturers_by_college.map(item => item.college),
                datasets: [{
                    label: 'Lecturers',
                    data: data.distributions.lecturers_by_college.map(item => item.lecturers),
                    backgroundColor: '#8b5cf6'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
}

function populateTopCollegesTable(colleges) {
    const tbody = document.getElementById('dashboard-top-colleges-tbody');
    if (!tbody) return;

    if (colleges && colleges.length > 0) {
        tbody.innerHTML = colleges.map((college, index) => `
            <tr>
                <td>${index + 1}</td>
                <td>${college.name || '-'}</td>
                <td>${college.students_count || 0}</td>
                <td>${college.lecturers_count || 0}</td>
                <td>${college.courses_count || 0}</td>
                <td><span class="badge badge-${college.status || 'pending'}">${college.status || 'pending'}</span></td>
                <td>
                    <button class="btn-icon btn-info" onclick="viewCollege(${college.id})" title="View">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    } else {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><i class="fas fa-inbox"></i><p>No colleges found</p></td></tr>';
    }
}

function populateRecentRegistrationsTable(registrations) {
    const tbody = document.getElementById('dashboard-recent-registrations-tbody');
    if (!tbody) return;

    if (registrations && registrations.length > 0) {
        tbody.innerHTML = registrations.map(reg => `
            <tr>
                <td>${reg.school_name || '-'}</td>
                <td>${reg.school_type || '-'}</td>
                <td>${reg.owner_name || '-'}</td>
                <td>${reg.email || '-'}</td>
                <td>${reg.date || '-'}</td>
                <td><span class="badge badge-${reg.status || 'pending'}">${reg.status || 'pending'}</span></td>
                <td>
                    <button class="btn-icon btn-info" onclick="viewRegistration(${reg.id})" title="View">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    } else {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state"><i class="fas fa-inbox"></i><p>No registrations found</p></td></tr>';
    }
}

async function loadSettings() {
    showLoading();
    try {
        // API: GET /api/superadmin/settings
        const data = await apiCall('/settings');
        if (data) {
            document.getElementById('platform-name').value = data.platform_name || 'SmartCampus';
            document.getElementById('default-status').value = data.default_status || 'pending';
            document.getElementById('system-email').value = data.system_email || '';
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    } finally {
        hideLoading();
    }
}

async function loadProfile() {
    showLoading();
    try {
        // API: GET /api/superadmin/profile
        const data = await apiCall('/profile');
        if (data) {
            document.getElementById('profile-name').value = data.name || '';
            document.getElementById('profile-email').value = data.email || '';
            document.getElementById('profile-phone').value = data.phone || '';
        } else {
            const user = getUser();
            if (user) {
                document.getElementById('profile-name').value = user.name || '';
                document.getElementById('profile-email').value = user.email || '';
            }
        }
    } catch (error) {
        console.error('Error loading profile:', error);
    } finally {
        hideLoading();
    }
}

function loadUserProfile() {
    const user = getUser();
    if (user) {
        const nameEl = document.getElementById('admin-name');
        if (nameEl) {
            nameEl.textContent = user.name || 'Super Admin';
        }
    }
}

// ============================================
// Tables Setup
// ============================================

function setupTables() {
    // Table setup can be extended here
}

// ============================================
// Clickable Cards Setup
// ============================================

function setupClickableCards() {
    const clickableCards = document.querySelectorAll('.clickable-card');
    clickableCards.forEach(card => {
        card.addEventListener('click', (e) => {
            const cardType = card.getAttribute('data-card-type');
            if (cardType) {
                if (cardType === 'colleges') {
                    openCollegesCardsModal();
                } else {
                    openDetailModal(cardType);
                }
            }
        });
    });
}

function setupDetailModal() {
    const modal = document.getElementById('detail-modal');
    const closeBtn = document.getElementById('detail-modal-close');
    const searchInput = document.getElementById('detail-search');
    
    if (!modal) return;
    
    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', closeDetailModal);
    }
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeDetailModal();
        }
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeDetailModal();
        }
    });
    
    // Search functionality
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const searchTerm = e.target.value.trim();
            detailModalData.searchTerm = searchTerm;
            detailModalData.currentPage = 1;
            
            searchTimeout = setTimeout(() => {
                if (detailModalData.type) {
                    loadDetailData(detailModalData.type, 1, searchTerm);
                }
            }, 500); // Debounce search
        });
    }
}

// ============================================
// Detail Modal Functions for Analytics Cards
// ============================================

let detailModalData = {
    type: null,
    currentPage: 1,
    totalPages: 1,
    searchTerm: '',
    allData: []
};

/**
 * Open detail modal for analytics card
 */
async function openDetailModal(cardType) {
    const modal = document.getElementById('detail-modal');
    const modalTitle = document.getElementById('detail-modal-title');
    const tableHead = document.getElementById('detail-table-head');
    const tableBody = document.getElementById('detail-table-body');
    
    if (!modal) return;
    
    // Set modal title based on card type
    const titles = {
        'students': 'All Students Across Colleges',
        'lecturers': 'All Lecturers Across Colleges',
        'colleges': 'All Colleges',
        'departments': 'All Departments'
    };
    
    modalTitle.textContent = titles[cardType] || 'Details';
    detailModalData.type = cardType;
    detailModalData.currentPage = 1;
    detailModalData.searchTerm = '';
    
    // Show loading state
    tableBody.innerHTML = `
        <tr>
            <td colspan="10" class="loading-row">
                <i class="fas fa-spinner fa-spin"></i> Loading...
            </td>
        </tr>
    `;
    
    // Show modal
    modal.classList.add('active');
    
    // Load data
    await loadDetailData(cardType);
}

/**
 * Load detail data from API
 */
async function loadDetailData(cardType, page = 1, search = '') {
    try {
        let endpoint = '';
        let responseData = null;
        
        switch(cardType) {
            case 'students':
                endpoint = `/students/detail/?page=${page}&page_size=50${search ? `&search=${encodeURIComponent(search)}` : ''}`;
                responseData = await apiCall(endpoint);
                if (responseData) {
                    populateStudentsTable(responseData);
                }
                break;
            case 'lecturers':
                endpoint = `/lecturers/detail/?page=${page}&page_size=50${search ? `&search=${encodeURIComponent(search)}` : ''}`;
                responseData = await apiCall(endpoint);
                if (responseData) {
                    populateLecturersTable(responseData);
                }
                break;
            case 'colleges':
                endpoint = `/colleges/detail/?page=${page}&page_size=50${search ? `&search=${encodeURIComponent(search)}` : ''}`;
                responseData = await apiCall(endpoint);
                if (responseData) {
                    populateCollegesTable(responseData);
                }
                break;
            case 'departments':
                // Departments can use colleges detail or a custom endpoint
                endpoint = `/colleges/detail/?page=${page}&page_size=50${search ? `&search=${encodeURIComponent(search)}` : ''}`;
                responseData = await apiCall(endpoint);
                if (responseData) {
                    populateCollegesTable(responseData);
                }
                break;
        }
    } catch (error) {
        console.error('Error loading detail data:', error);
        const tableBody = document.getElementById('detail-table-body');
        tableBody.innerHTML = `
            <tr>
                <td colspan="10" class="error-row">
                    <i class="fas fa-exclamation-triangle"></i> Error loading data. Please try again.
                </td>
            </tr>
        `;
    }
}

/**
 * Populate students table
 */
function populateStudentsTable(data) {
    const tableHead = document.getElementById('detail-table-head');
    const tableBody = document.getElementById('detail-table-body');
    const totalCount = document.getElementById('detail-total-count');
    
    totalCount.textContent = data.total || 0;
    detailModalData.currentPage = data.page || 1;
    detailModalData.totalPages = data.total_pages || 1;
    
    // Set table header
    tableHead.innerHTML = `
        <tr>
            <th>Admission Number</th>
            <th>Full Name</th>
            <th>Email</th>
            <th>Course</th>
            <th>Year</th>
            <th>College Name</th>
            <th>College Location</th>
            <th>Actions</th>
        </tr>
    `;
    
    // Populate table body
    if (data.students && data.students.length > 0) {
        tableBody.innerHTML = data.students.map(student => `
            <tr>
                <td>${student.admission_number || '-'}</td>
                <td>${student.full_name || '-'}</td>
                <td>${student.email || '-'}</td>
                <td>${student.course || 'Not Assigned'}</td>
                <td>${student.year || '-'}</td>
                <td>${student.college_name || '-'}</td>
                <td>${student.college_location || '-'}</td>
                <td>
                    <button class="btn-icon btn-info" title="View College" onclick="viewCollegeDetail(${student.college_id})">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    } else {
        tableBody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state">
                    <i class="fas fa-user-graduate"></i>
                    <p>No students found</p>
                </td>
            </tr>
        `;
    }
    
    // Update pagination
    updateDetailPagination();
}

/**
 * Populate lecturers table
 */
function populateLecturersTable(data) {
    const tableHead = document.getElementById('detail-table-head');
    const tableBody = document.getElementById('detail-table-body');
    const totalCount = document.getElementById('detail-total-count');
    
    totalCount.textContent = data.total || 0;
    detailModalData.currentPage = data.page || 1;
    detailModalData.totalPages = data.total_pages || 1;
    
    // Set table header
    tableHead.innerHTML = `
        <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Phone</th>
            <th>College Name</th>
            <th>College Location</th>
            <th>Assigned Units</th>
            <th>Actions</th>
        </tr>
    `;
    
    // Populate table body
    if (data.lecturers && data.lecturers.length > 0) {
        tableBody.innerHTML = data.lecturers.map(lecturer => `
            <tr>
                <td>${lecturer.full_name || lecturer.username || '-'}</td>
                <td>${lecturer.email || '-'}</td>
                <td>${lecturer.phone || '-'}</td>
                <td>${lecturer.college_name || 'No College'}</td>
                <td>${lecturer.college_location || '-'}</td>
                <td>${lecturer.assigned_units_count || 0}</td>
                <td>
                    ${lecturer.college_id ? `
                        <button class="btn-icon btn-info" title="View College" onclick="viewCollegeDetail(${lecturer.college_id})">
                            <i class="fas fa-eye"></i>
                        </button>
                    ` : '-'}
                </td>
            </tr>
        `).join('');
    } else {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">
                    <i class="fas fa-chalkboard-teacher"></i>
                    <p>No lecturers found</p>
                </td>
            </tr>
        `;
    }
    
    // Update pagination
    updateDetailPagination();
}

/**
 * Populate colleges table
 */
function populateCollegesTable(data) {
    const tableHead = document.getElementById('detail-table-head');
    const tableBody = document.getElementById('detail-table-body');
    const totalCount = document.getElementById('detail-total-count');
    
    totalCount.textContent = data.total || 0;
    detailModalData.currentPage = data.page || 1;
    detailModalData.totalPages = data.total_pages || 1;
    
    // Set table header
    tableHead.innerHTML = `
        <tr>
            <th>College Name</th>
            <th>Principal/Owner</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Location</th>
            <th>Status</th>
            <th>Students</th>
            <th>Lecturers</th>
            <th>Actions</th>
        </tr>
    `;
    
    // Populate table body
    if (data.colleges && data.colleges.length > 0) {
        tableBody.innerHTML = data.colleges.map(college => `
            <tr>
                <td>${college.name || '-'}</td>
                <td>${college.principal_name || '-'}</td>
                <td>${college.email || '-'}</td>
                <td>${college.phone || '-'}</td>
                <td>${college.location || '-'}</td>
                <td>
                    <span class="badge badge-${college.status}">${college.status_display || college.status}</span>
                </td>
                <td>${college.students_count || 0}</td>
                <td>${college.lecturers_count || 0}</td>
                <td>
                    <button class="btn-icon btn-info" title="View" onclick="viewCollegeDetail(${college.id})">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    } else {
        tableBody.innerHTML = `
            <tr>
                <td colspan="9" class="empty-state">
                    <i class="fas fa-school"></i>
                    <p>No colleges found</p>
                </td>
            </tr>
        `;
    }
    
    // Update pagination
    updateDetailPagination();
}

/**
 * Update detail modal pagination
 */
function updateDetailPagination() {
    const pagination = document.getElementById('detail-pagination');
    if (!pagination) return;
    
    if (detailModalData.totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    
    // Previous button
    if (detailModalData.currentPage > 1) {
        html += `<button class="btn btn-sm btn-secondary" onclick="goToDetailPage(${detailModalData.currentPage - 1})">
            <i class="fas fa-chevron-left"></i> Previous
        </button>`;
    }
    
    // Page info
    html += `<span class="pagination-info">Page ${detailModalData.currentPage} of ${detailModalData.totalPages}</span>`;
    
    // Next button
    if (detailModalData.currentPage < detailModalData.totalPages) {
        html += `<button class="btn btn-sm btn-secondary" onclick="goToDetailPage(${detailModalData.currentPage + 1})">
            Next <i class="fas fa-chevron-right"></i>
        </button>`;
    }
    
    html += '</div>';
    pagination.innerHTML = html;
}

/**
 * Go to specific page in detail modal
 */
function goToDetailPage(page) {
    if (page < 1 || page > detailModalData.totalPages) return;
    detailModalData.currentPage = page;
    loadDetailData(detailModalData.type, page, detailModalData.searchTerm);
}

/**
 * View college detail (redirect to colleges page or show modal)
 */
function viewCollegeDetail(collegeId) {
    // Navigate to colleges page and highlight the college
    if (window.switchPage) {
        window.switchPage('colleges');
        // Could add logic to scroll to or highlight the college
    }
}

/**
 * Close detail modal
 */
function closeDetailModal() {
    const modal = document.getElementById('detail-modal');
    if (modal) {
        modal.classList.remove('active');
        detailModalData.type = null;
        detailModalData.currentPage = 1;
        detailModalData.searchTerm = '';
    }
}

// ============================================
// Colleges Cards Modal Functions
// ============================================

let collegesCardsData = {
    currentPage: 1,
    totalPages: 1,
    searchTerm: '',
    colleges: []
};

/**
 * Open colleges cards modal
 */
async function openCollegesCardsModal() {
    const modal = document.getElementById('colleges-cards-modal');
    if (!modal) return;
    
    collegesCardsData.currentPage = 1;
    collegesCardsData.searchTerm = '';
    
    // Reset search input
    const searchInput = document.getElementById('colleges-cards-search');
    if (searchInput) {
        searchInput.value = '';
    }
    
    // Show loading state
    const container = document.getElementById('colleges-cards-container');
    if (container) {
        container.innerHTML = '<div class="loading-row"><i class="fas fa-spinner fa-spin"></i> Loading colleges...</div>';
    }
    
    // Show modal
    modal.classList.add('active');
    
    // Load colleges
    await loadCollegesCards();
}

/**
 * Load colleges cards from API
 */
async function loadCollegesCards(page = 1, search = '') {
    try {
        const params = new URLSearchParams({
            page: page,
            page_size: 20,
        });
        
        if (search) {
            params.append('search', search);
        }
        
        const responseData = await apiCall(`/colleges/cards/?${params}`);
        
        if (responseData && responseData.colleges) {
            collegesCardsData.colleges = responseData.colleges;
            collegesCardsData.currentPage = responseData.page || 1;
            collegesCardsData.totalPages = responseData.total_pages || 1;
            
            renderCollegesCards(responseData.colleges);
            renderCollegesCardsPagination(responseData);
            updateCollegesCardsStats(responseData.total || 0);
        } else {
            const container = document.getElementById('colleges-cards-container');
            if (container) {
                container.innerHTML = '<div class="loading-row">No colleges found</div>';
            }
        }
    } catch (error) {
        console.error('Error loading colleges cards:', error);
        const container = document.getElementById('colleges-cards-container');
        if (container) {
            container.innerHTML = '<div class="error-row"><i class="fas fa-exclamation-triangle"></i> Error loading colleges. Please try again.</div>';
        }
    }
}

/**
 * Render colleges cards
 */
function renderCollegesCards(colleges) {
    const container = document.getElementById('colleges-cards-container');
    if (!container) return;
    
    if (!colleges || colleges.length === 0) {
        container.innerHTML = '<div class="loading-row">No colleges found</div>';
        return;
    }
    
    let html = '<div class="colleges-cards-grid">';
    
    colleges.forEach(college => {
        const statusClass = college.status === 'active' ? 'active' : 
                           college.status === 'inactive' ? 'inactive' : 'pending';
        const statusIcon = college.status === 'active' ? 'fa-check-circle' : 
                          college.status === 'inactive' ? 'fa-ban' : 'fa-clock';
        
        html += `
            <div class="college-card" data-college-id="${college.id}">
                <div class="college-card-header">
                    <div class="college-card-status status-${statusClass}">
                        <i class="fas ${statusIcon}"></i>
                        <span>${college.status_display}</span>
                    </div>
                </div>
                <div class="college-card-body">
                    <h3 class="college-card-name">${escapeHtml(college.name)}</h3>
                    <div class="college-card-info">
                        <div class="college-card-info-item">
                            <i class="fas fa-user-tie"></i>
                            <span>${escapeHtml(college.owner_name || 'N/A')}</span>
                        </div>
                        <div class="college-card-info-item">
                            <i class="fas fa-user-graduate"></i>
                            <span>${college.active_students || 0} Active Students</span>
                        </div>
                    </div>
                </div>
                <div class="college-card-footer">
                    <button class="btn btn-sm btn-primary view-college-detail" data-college-id="${college.id}">
                        <i class="fas fa-eye"></i> View Details
                    </button>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
    
    // Attach click handlers
    attachCollegesCardsHandlers();
}

/**
 * Attach event handlers to college cards
 */
function attachCollegesCardsHandlers() {
    // View detail buttons
    const viewButtons = document.querySelectorAll('.view-college-detail');
    viewButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const collegeId = btn.getAttribute('data-college-id');
            if (collegeId) {
                openCollegeDetailModal(parseInt(collegeId));
            }
        });
    });
    
    // Card click to view details
    const cards = document.querySelectorAll('.college-card');
    cards.forEach(card => {
        card.addEventListener('click', (e) => {
            // Don't trigger if clicking on button
            if (e.target.closest('.view-college-detail')) return;
            
            const collegeId = card.getAttribute('data-college-id');
            if (collegeId) {
                openCollegeDetailModal(parseInt(collegeId));
            }
        });
    });
}

/**
 * Render pagination for colleges cards
 */
function renderCollegesCardsPagination(data) {
    const pagination = document.getElementById('colleges-cards-pagination');
    if (!pagination || !data || data.total_pages <= 1) {
        if (pagination) pagination.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    
    // Previous button
    if (data.previous) {
        html += `<button class="pagination-btn" onclick="goToCollegesCardsPage(${data.previous})">
            <i class="fas fa-chevron-left"></i> Previous
        </button>`;
    } else {
        html += `<button class="pagination-btn disabled" disabled>
            <i class="fas fa-chevron-left"></i> Previous
        </button>`;
    }
    
    // Page numbers
    const currentPage = data.page || 1;
    const totalPages = data.total_pages || 1;
    
    for (let i = 1; i <= totalPages; i++) {
        if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
            html += `<button class="pagination-btn ${i === currentPage ? 'active' : ''}" 
                onclick="goToCollegesCardsPage(${i})">${i}</button>`;
        } else if (i === currentPage - 3 || i === currentPage + 3) {
            html += `<span class="pagination-ellipsis">...</span>`;
        }
    }
    
    // Next button
    if (data.next) {
        html += `<button class="pagination-btn" onclick="goToCollegesCardsPage(${data.next})">
            Next <i class="fas fa-chevron-right"></i>
        </button>`;
    } else {
        html += `<button class="pagination-btn disabled" disabled>
            Next <i class="fas fa-chevron-right"></i>
        </button>`;
    }
    
    html += '</div>';
    pagination.innerHTML = html;
}

/**
 * Go to specific page in colleges cards
 */
function goToCollegesCardsPage(page) {
    if (page < 1 || page > collegesCardsData.totalPages) return;
    collegesCardsData.currentPage = page;
    loadCollegesCards(page, collegesCardsData.searchTerm);
}

/**
 * Update colleges cards stats
 */
function updateCollegesCardsStats(total) {
    const statsEl = document.getElementById('colleges-cards-total-count');
    if (statsEl) {
        statsEl.textContent = total || 0;
    }
}

/**
 * Close colleges cards modal
 */
function closeCollegesCardsModal() {
    const modal = document.getElementById('colleges-cards-modal');
    if (modal) {
        modal.classList.remove('active');
        collegesCardsData.currentPage = 1;
        collegesCardsData.searchTerm = '';
    }
}

/**
 * Setup colleges cards modal
 */
function setupCollegesCardsModal() {
    const modal = document.getElementById('colleges-cards-modal');
    const closeBtn = document.getElementById('colleges-cards-modal-close');
    const searchInput = document.getElementById('colleges-cards-search');
    
    if (!modal) return;
    
    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', closeCollegesCardsModal);
    }
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeCollegesCardsModal();
        }
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeCollegesCardsModal();
        }
    });
    
    // Search functionality
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            const searchTerm = e.target.value.trim();
            collegesCardsData.searchTerm = searchTerm;
            collegesCardsData.currentPage = 1;
            
            searchTimeout = setTimeout(() => {
                loadCollegesCards(1, searchTerm);
            }, 500); // Debounce search
        });
    }
}

/**
 * Open college detail modal
 */
async function openCollegeDetailModal(collegeId) {
    const modal = document.getElementById('college-detail-modal');
    const titleEl = document.getElementById('college-detail-title');
    const bodyEl = document.getElementById('college-detail-body');
    const suspendBtn = document.getElementById('college-detail-suspend-btn');
    const activateBtn = document.getElementById('college-detail-activate-btn');
    
    if (!modal) return;
    
    // Show loading state
    if (bodyEl) {
        bodyEl.innerHTML = '<div class="loading-row"><i class="fas fa-spinner fa-spin"></i> Loading college details...</div>';
    }
    
    // Show modal
    modal.classList.add('active');
    
    try {
        // Fetch college details
        const responseData = await apiCall(`/colleges/${collegeId}/`);
        
        if (responseData && responseData.college) {
            const college = responseData.college;
            
            // Update title
            if (titleEl) {
                titleEl.textContent = college.name || 'College Details';
            }
            
            // Render college details
            if (bodyEl) {
                let html = `
                    <div class="college-detail-content">
                        <div class="college-detail-section">
                            <h3><i class="fas fa-info-circle"></i> Basic Information</h3>
                            <div class="detail-grid">
                                <div class="detail-item">
                                    <label>College Name:</label>
                                    <span>${escapeHtml(college.name || 'N/A')}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Owner/Principal:</label>
                                    <span>${escapeHtml(college.principal_name || college.owner || 'N/A')}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Email:</label>
                                    <span>${escapeHtml(college.email || 'N/A')}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Phone:</label>
                                    <span>${escapeHtml(college.phone || 'N/A')}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Location:</label>
                                    <span>${escapeHtml(college.location || college.county || 'N/A')}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Address:</label>
                                    <span>${escapeHtml(college.address || 'N/A')}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Status:</label>
                                    <span class="badge badge-${college.status || 'pending'}">${college.status_display || 'Pending'}</span>
                                </div>
                            </div>
                        </div>
                        <div class="college-detail-section">
                            <h3><i class="fas fa-chart-bar"></i> Statistics</h3>
                            <div class="detail-grid">
                                <div class="detail-item">
                                    <label>Total Students:</label>
                                    <span>${college.students_count || 0}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Active Students:</label>
                                    <span>${college.active_students || 0}</span>
                                </div>
                                <div class="detail-item">
                                    <label>Lecturers:</label>
                                    <span>${college.lecturers_count || 0}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                bodyEl.innerHTML = html;
            }
            
            // Show/hide suspend/activate buttons
            if (suspendBtn && activateBtn) {
                if (college.status === 'active') {
                    suspendBtn.style.display = 'inline-block';
                    activateBtn.style.display = 'none';
                    suspendBtn.setAttribute('data-college-id', collegeId);
                } else if (college.status === 'inactive') {
                    suspendBtn.style.display = 'none';
                    activateBtn.style.display = 'inline-block';
                    activateBtn.setAttribute('data-college-id', collegeId);
                } else {
                    suspendBtn.style.display = 'none';
                    activateBtn.style.display = 'none';
                }
            }
        } else {
            if (bodyEl) {
                bodyEl.innerHTML = '<div class="error-row"><i class="fas fa-exclamation-triangle"></i> Error loading college details.</div>';
            }
        }
    } catch (error) {
        console.error('Error loading college details:', error);
        if (bodyEl) {
            bodyEl.innerHTML = '<div class="error-row"><i class="fas fa-exclamation-triangle"></i> Error loading college details. Please try again.</div>';
        }
    }
}

/**
 * Setup college detail modal
 */
function setupCollegeDetailModal() {
    const modal = document.getElementById('college-detail-modal');
    const closeBtn = document.getElementById('college-detail-modal-close');
    const closeBtnFooter = document.getElementById('college-detail-close-btn');
    const suspendBtn = document.getElementById('college-detail-suspend-btn');
    const activateBtn = document.getElementById('college-detail-activate-btn');
    
    if (!modal) return;
    
    // Close modal handlers
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    }
    
    if (closeBtnFooter) {
        closeBtnFooter.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    }
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            modal.classList.remove('active');
        }
    });
    
    // Suspend button
    if (suspendBtn) {
        suspendBtn.addEventListener('click', async (e) => {
            const collegeId = suspendBtn.getAttribute('data-college-id');
            if (collegeId && confirm('Are you sure you want to suspend this college?')) {
                try {
                    await suspendCollege(parseInt(collegeId));
                    // Reload college details
                    await openCollegeDetailModal(parseInt(collegeId));
                    // Refresh colleges cards if modal is open
                    if (document.getElementById('colleges-cards-modal').classList.contains('active')) {
                        await loadCollegesCards(collegesCardsData.currentPage, collegesCardsData.searchTerm);
                    }
                } catch (error) {
                    console.error('Error suspending college:', error);
                }
            }
        });
    }
    
    // Activate button
    if (activateBtn) {
        activateBtn.addEventListener('click', async (e) => {
            const collegeId = activateBtn.getAttribute('data-college-id');
            if (collegeId && confirm('Are you sure you want to activate this college?')) {
                try {
                    // Use approve endpoint to activate
                    const response = await apiCall(`/colleges/${collegeId}/approve/`, {
                        method: 'POST'
                    });
                    if (response && response.success) {
                        showToast('success', 'College activated successfully');
                        // Reload college details
                        await openCollegeDetailModal(parseInt(collegeId));
                        // Refresh colleges cards if modal is open
                        if (document.getElementById('colleges-cards-modal').classList.contains('active')) {
                            await loadCollegesCards(collegesCardsData.currentPage, collegesCardsData.searchTerm);
                        }
                    }
                } catch (error) {
                    console.error('Error activating college:', error);
                    showToast('error', 'Error activating college');
                }
            }
        });
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Make functions globally available
window.apiCall = apiCall;
window.showToast = showToast;
window.approveCollege = approveCollege;
window.suspendCollege = suspendCollege;
window.editCollege = editCollege;
window.deleteCollege = deleteCollege;
window.viewCollege = viewCollege;
window.goToPage = goToPage;
window.openCollegeModal = openCollegeModal;
window.openDetailModal = openDetailModal;
window.goToDetailPage = goToDetailPage;
window.viewCollegeDetail = viewCollegeDetail;
window.closeDetailModal = closeDetailModal;
window.openCollegesCardsModal = openCollegesCardsModal;
window.goToCollegesCardsPage = goToCollegesCardsPage;
window.openCollegeDetailModal = openCollegeDetailModal;

