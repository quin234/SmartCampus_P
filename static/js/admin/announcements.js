/**
 * Announcements Management JavaScript
 */

let announcementsData = [];
let currentPage = 1;
const itemsPerPage = 10;
let studentsList = [];
let lecturersList = [];
let editingAnnouncementId = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkAuth();
    loadAnnouncements();
    loadStudentsAndLecturers();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // FAB button
    document.getElementById('fab-add-announcement').addEventListener('click', () => {
        openCreateModal();
    });

    // Modal close buttons
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('modal-cancel').addEventListener('click', closeModal);
    document.getElementById('view-modal-close').addEventListener('click', closeViewModal);
    document.getElementById('view-modal-close-btn').addEventListener('click', closeViewModal);

    // Form submission
    document.getElementById('announcement-form').addEventListener('submit', handleFormSubmit);

    // Target type change
    document.getElementById('announcement-target-type').addEventListener('change', handleTargetTypeChange);

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchTab(e.target.dataset.tab);
        });
    });

    // Multi-select change handlers
    document.getElementById('announcement-targeted-students').addEventListener('change', updateSelectedCount);
    document.getElementById('announcement-targeted-users').addEventListener('change', updateSelectedCount);

    // Filters
    document.getElementById('search-input').addEventListener('input', debounce(loadAnnouncements, 300));
    document.getElementById('target-type-filter').addEventListener('change', loadAnnouncements);
    document.getElementById('priority-filter').addEventListener('change', loadAnnouncements);
    document.getElementById('status-filter').addEventListener('change', loadAnnouncements);

    // Profile dropdown
    const profileBtn = document.getElementById('profile-btn');
    const profileMenu = document.getElementById('profile-menu');
    if (profileBtn && profileMenu) {
        profileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            profileMenu.classList.toggle('show');
        });
        document.addEventListener('click', () => {
            profileMenu.classList.remove('show');
        });
    }
}

// Load announcements
async function loadAnnouncements() {
    showLoading();
    try {
        const params = new URLSearchParams({
            page: currentPage,
            page_size: itemsPerPage
        });

        const search = document.getElementById('search-input').value;
        if (search) params.append('search', search);

        const targetType = document.getElementById('target-type-filter').value;
        if (targetType) params.append('target_type', targetType);

        const priority = document.getElementById('priority-filter').value;
        if (priority) params.append('priority', priority);

        const status = document.getElementById('status-filter').value;
        if (status !== '') params.append('is_active', status);

        const data = await apiCall(`announcements/?${params}`);
        
        if (data && data.results) {
            announcementsData = data.results;
            renderAnnouncementsTable(announcementsData);
            renderPagination('pagination', data.page, data.total_pages, (page) => {
                currentPage = page;
                loadAnnouncements();
            });
            document.getElementById('announcements-count').textContent = `${data.count} announcement${data.count !== 1 ? 's' : ''}`;
        } else {
            announcementsData = [];
            renderAnnouncementsTable([]);
            renderPagination('pagination', 1, 1);
            document.getElementById('announcements-count').textContent = '0 announcements';
        }
    } catch (error) {
        console.error('Error loading announcements:', error);
        showToast('error', 'Failed to load announcements');
        renderAnnouncementsTable([]);
    }
}

// Render announcements table
function renderAnnouncementsTable(announcements) {
    const tbody = document.getElementById('announcements-tbody');
    
    if (announcements.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No announcements found</td></tr>';
        return;
    }

    tbody.innerHTML = announcements.map(ann => {
        const priorityBadge = getPriorityBadge(ann.priority);
        const targetBadge = getTargetBadge(ann.target_type, ann.targeted_students?.length || 0, ann.targeted_users?.length || 0);
        const statusBadge = ann.is_active 
            ? '<span class="badge badge-success">Active</span>' 
            : '<span class="badge badge-secondary">Inactive</span>';
        const expiredBadge = ann.is_expired ? '<span class="badge badge-warning">Expired</span>' : '';
        
        return `
            <tr>
                <td><strong>${escapeHtml(ann.title)}</strong></td>
                <td>${targetBadge}</td>
                <td>${priorityBadge}</td>
                <td>${escapeHtml(ann.created_by || 'Unknown')}</td>
                <td>${formatDate(ann.created_at)}</td>
                <td>${statusBadge} ${expiredBadge}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-icon btn-view" onclick="viewAnnouncement(${ann.id})" title="View">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn-icon btn-edit" onclick="editAnnouncement(${ann.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn-icon btn-delete" onclick="deleteAnnouncement(${ann.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

// Get priority badge HTML
function getPriorityBadge(priority) {
    const badges = {
        'urgent': '<span class="badge badge-urgent"><i class="fas fa-exclamation-circle"></i> Urgent</span>',
        'high': '<span class="badge badge-high"><i class="fas fa-exclamation-triangle"></i> High</span>',
        'normal': '<span class="badge badge-normal">Normal</span>'
    };
    return badges[priority] || badges.normal;
}

// Get target badge HTML
function getTargetBadge(targetType, studentsCount, usersCount) {
    const badges = {
        'all_students': '<span class="badge badge-target-all-students">All Students</span>',
        'all_lecturers': '<span class="badge badge-target-all-lecturers">All Lecturers</span>',
        'individual': `<span class="badge badge-target-individual">Individual (${studentsCount + usersCount} users)</span>`
    };
    return badges[targetType] || '';
}

// Load students and lecturers for individual targeting
async function loadStudentsAndLecturers() {
    try {
        // Load students
        const studentsData = await apiCall('students/');
        if (studentsData && studentsData.results) {
            studentsList = studentsData.results;
            populateStudentsSelect();
        }

        // Load lecturers
        const lecturersData = await apiCall('lecturers/');
        if (lecturersData && lecturersData.results) {
            lecturersList = lecturersData.results;
            populateLecturersSelect();
        }
    } catch (error) {
        console.error('Error loading students/lecturers:', error);
    }
}

// Populate students select
function populateStudentsSelect() {
    const select = document.getElementById('announcement-targeted-students');
    select.innerHTML = studentsList.map(student => 
        `<option value="${student.id}">${escapeHtml(student.admission_number)} - ${escapeHtml(student.full_name)}</option>`
    ).join('');
}

// Populate lecturers select
function populateLecturersSelect() {
    const select = document.getElementById('announcement-targeted-users');
    select.innerHTML = lecturersList.map(lecturer => 
        `<option value="${lecturer.id}">${escapeHtml(lecturer.username)} - ${escapeHtml(lecturer.full_name || lecturer.email || '')}</option>`
    ).join('');
}

// Handle target type change
function handleTargetTypeChange() {
    const targetType = document.getElementById('announcement-target-type').value;
    const individualSection = document.getElementById('individual-targeting-section');
    
    if (targetType === 'individual') {
        individualSection.style.display = 'block';
    } else {
        individualSection.style.display = 'none';
        // Clear selections
        document.getElementById('announcement-targeted-students').selectedIndex = -1;
        document.getElementById('announcement-targeted-users').selectedIndex = -1;
        updateSelectedCount();
    }
}

// Update selected count
function updateSelectedCount() {
    const studentsSelect = document.getElementById('announcement-targeted-students');
    const usersSelect = document.getElementById('announcement-targeted-users');
    
    const studentsCount = Array.from(studentsSelect.selectedOptions).length;
    const usersCount = Array.from(usersSelect.selectedOptions).length;
    
    document.getElementById('selected-students-count').textContent = `${studentsCount} student${studentsCount !== 1 ? 's' : ''}`;
    document.getElementById('selected-lecturers-count').textContent = `${usersCount} lecturer${usersCount !== 1 ? 's' : ''}`;
}

// Switch tabs
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
    
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(tabName).classList.add('active');
}

// Open create modal
function openCreateModal() {
    editingAnnouncementId = null;
    document.getElementById('modal-title').textContent = 'Create New Announcement';
    document.getElementById('modal-submit').textContent = 'Create Announcement';
    document.getElementById('announcement-form').reset();
    document.getElementById('announcement-id').value = '';
    document.getElementById('individual-targeting-section').style.display = 'none';
    document.getElementById('announcement-modal').classList.add('active');
}

// Open edit modal
async function editAnnouncement(id) {
    try {
        const data = await apiCall(`announcements/${id}/`);
        
        editingAnnouncementId = id;
        document.getElementById('modal-title').textContent = 'Edit Announcement';
        document.getElementById('modal-submit').textContent = 'Update Announcement';
        document.getElementById('announcement-id').value = id;
        document.getElementById('announcement-title').value = data.title || '';
        document.getElementById('announcement-content').value = data.content || '';
        document.getElementById('announcement-target-type').value = data.target_type || '';
        document.getElementById('announcement-priority').value = data.priority || 'normal';
        
        // Set expiration date
        if (data.expires_at) {
            const date = new Date(data.expires_at);
            const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
            document.getElementById('announcement-expires-at').value = localDate.toISOString().slice(0, 16);
        } else {
            document.getElementById('announcement-expires-at').value = '';
        }
        
        // Handle individual targeting
        handleTargetTypeChange();
        if (data.target_type === 'individual') {
            // Set selected students
            const studentsSelect = document.getElementById('announcement-targeted-students');
            Array.from(studentsSelect.options).forEach(option => {
                option.selected = data.targeted_students.includes(parseInt(option.value));
            });
            
            // Set selected lecturers
            const usersSelect = document.getElementById('announcement-targeted-users');
            Array.from(usersSelect.options).forEach(option => {
                option.selected = data.targeted_users.includes(parseInt(option.value));
            });
            updateSelectedCount();
        }
        
        document.getElementById('announcement-modal').classList.add('active');
    } catch (error) {
        console.error('Error loading announcement:', error);
        showToast('error', 'Failed to load announcement details');
    }
}

// View announcement
async function viewAnnouncement(id) {
    try {
        const data = await apiCall(`announcements/${id}/`);
        
        const content = `
            <div class="announcement-view">
                <div class="view-field">
                    <label>Title:</label>
                    <div class="view-value"><strong>${escapeHtml(data.title)}</strong></div>
                </div>
                <div class="view-field">
                    <label>Content:</label>
                    <div class="view-value">${escapeHtml(data.content).replace(/\n/g, '<br>')}</div>
                </div>
                <div class="view-field">
                    <label>Target Type:</label>
                    <div class="view-value">${getTargetBadge(data.target_type, data.targeted_students?.length || 0, data.targeted_users?.length || 0)}</div>
                </div>
                <div class="view-field">
                    <label>Priority:</label>
                    <div class="view-value">${getPriorityBadge(data.priority)}</div>
                </div>
                <div class="view-field">
                    <label>Created By:</label>
                    <div class="view-value">${escapeHtml(data.created_by || 'Unknown')}</div>
                </div>
                <div class="view-field">
                    <label>Created At:</label>
                    <div class="view-value">${formatDate(data.created_at)}</div>
                </div>
                ${data.expires_at ? `
                <div class="view-field">
                    <label>Expires At:</label>
                    <div class="view-value">${formatDate(data.expires_at)} ${data.is_expired ? '<span class="badge badge-warning">Expired</span>' : ''}</div>
                </div>
                ` : ''}
                <div class="view-field">
                    <label>Status:</label>
                    <div class="view-value">${data.is_active ? '<span class="badge badge-success">Active</span>' : '<span class="badge badge-secondary">Inactive</span>'}</div>
                </div>
                ${data.target_type === 'individual' ? `
                <div class="view-field">
                    <label>Targeted Students:</label>
                    <div class="view-value">${data.targeted_students.length} student(s)</div>
                </div>
                <div class="view-field">
                    <label>Targeted Lecturers:</label>
                    <div class="view-value">${data.targeted_users.length} lecturer(s)</div>
                </div>
                ` : ''}
            </div>
        `;
        
        document.getElementById('view-announcement-content').innerHTML = content;
        document.getElementById('view-announcement-modal').classList.add('active');
    } catch (error) {
        console.error('Error loading announcement:', error);
        showToast('error', 'Failed to load announcement details');
    }
}

// Handle form submission
async function handleFormSubmit(e) {
    e.preventDefault();
    
    // Clear previous errors
    clearFieldErrors();
    
    // Validate form
    if (!validateForm()) {
        return;
    }
    
    try {
        const formData = {
            title: document.getElementById('announcement-title').value.trim(),
            content: document.getElementById('announcement-content').value.trim(),
            target_type: document.getElementById('announcement-target-type').value,
            priority: document.getElementById('announcement-priority').value,
            expires_at: document.getElementById('announcement-expires-at').value || null
        };
        
        // Handle individual targeting
        if (formData.target_type === 'individual') {
            const studentsSelect = document.getElementById('announcement-targeted-students');
            const usersSelect = document.getElementById('announcement-targeted-users');
            
            formData.targeted_students = Array.from(studentsSelect.selectedOptions).map(opt => parseInt(opt.value));
            formData.targeted_users = Array.from(usersSelect.selectedOptions).map(opt => parseInt(opt.value));
            
            if (formData.targeted_students.length === 0 && formData.targeted_users.length === 0) {
                showFieldError('individual-targeting-error', 'At least one student or lecturer must be selected');
                return;
            }
        }
        
        // Format expiration date for API
        if (formData.expires_at) {
            const date = new Date(formData.expires_at);
            formData.expires_at = date.toISOString();
        }
        
        let response;
        if (editingAnnouncementId) {
            // Update
            response = await apiCall(`announcements/${editingAnnouncementId}/`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
        } else {
            // Create
            response = await apiCall('announcements/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
        }
        
        showToast('success', editingAnnouncementId ? 'Announcement updated successfully' : 'Announcement created successfully');
        closeModal();
        loadAnnouncements();
    } catch (error) {
        console.error('Error saving announcement:', error);
        if (error.errors) {
            // Display field-specific errors
            Object.keys(error.errors).forEach(field => {
                showFieldError(`${field}-error`, error.errors[field]);
            });
        } else {
            showToast('error', error.message || 'Failed to save announcement');
        }
    }
}

// Validate form
function validateForm() {
    let isValid = true;
    
    const title = document.getElementById('announcement-title').value.trim();
    if (!title) {
        showFieldError('title-error', 'Title is required');
        isValid = false;
    }
    
    const content = document.getElementById('announcement-content').value.trim();
    if (!content) {
        showFieldError('content-error', 'Content is required');
        isValid = false;
    }
    
    const targetType = document.getElementById('announcement-target-type').value;
    if (!targetType) {
        showFieldError('target-type-error', 'Target type is required');
        isValid = false;
    }
    
    return isValid;
}

// Delete announcement
async function deleteAnnouncement(id) {
    if (!confirm('Are you sure you want to delete this announcement? This will deactivate it.')) {
        return;
    }
    
    try {
        await apiCall(`announcements/${id}/`, {
            method: 'DELETE'
        });
        showToast('success', 'Announcement deleted successfully');
        loadAnnouncements();
    } catch (error) {
        console.error('Error deleting announcement:', error);
        showToast('error', 'Failed to delete announcement');
    }
}

// Close modal
function closeModal() {
    document.getElementById('announcement-modal').classList.remove('active');
    document.getElementById('announcement-form').reset();
    editingAnnouncementId = null;
    clearFieldErrors();
}

// Close view modal
function closeViewModal() {
    document.getElementById('view-announcement-modal').classList.remove('active');
}

// Utility functions
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showLoading() {
    const tbody = document.getElementById('announcements-tbody');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="7" class="loading-row"><i class="fas fa-spinner fa-spin"></i> Loading...</td></tr>';
    }
}

function clearFieldErrors() {
    document.querySelectorAll('.field-error').forEach(el => {
        el.textContent = '';
        el.style.display = 'none';
    });
}

// Make functions globally available
window.viewAnnouncement = viewAnnouncement;
window.editAnnouncement = editAnnouncement;
window.deleteAnnouncement = deleteAnnouncement;

