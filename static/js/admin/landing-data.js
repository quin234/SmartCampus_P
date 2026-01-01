/**
 * Landing Page Data Management
 * Handles CRUD operations for Students, Courses, and Units
 */

(function() {
    'use strict';

    // Helper function to format text to Title Case (sentence case)
    function formatToTitleCase(text) {
        if (!text || typeof text !== 'string') return text || '-';
        return text.toLowerCase().split(' ').map(word => 
            word.charAt(0).toUpperCase() + word.slice(1)
        ).join(' ');
    }

    // State management
    const state = {
        students: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            loading: false
        },
        courses: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            loading: false
        },
        units: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            loading: false
        },
        departments: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            loading: false,
            expandedDepartments: new Set()  // Track which departments are expanded
        },
        lecturers: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            loading: false
        },
        enrollments: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            totalCount: 0,
            loading: false
        },
        results: {
            data: [],
            currentPage: 1,
            totalPages: 1,
            loading: false
        }
    };

    // Get college slug from window (set by template)
    function getCollegeSlug() {
        return window.COLLEGE_SLUG || '';
    }

    // Build API endpoint
    function buildApiEndpoint(endpoint) {
        const collegeSlug = getCollegeSlug();
        if (!collegeSlug) {
            throw new Error('College slug not found');
        }
        return `/api/${collegeSlug}/${endpoint}`;
    }

    // Get CSRF token
    function getCSRFToken() {
        return window.csrftoken || getCookie('csrftoken');
    }

    // Get cookie helper
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

    // API call helper
    async function apiCall(endpoint, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken() || '',
            },
            credentials: 'same-origin'
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
            const response = await fetch(buildApiEndpoint(endpoint), config);
            
            // Handle 204 No Content (DELETE operations)
            if (response.status === 204) {
                return { success: true };
            }
            
            // Handle 401/403 before trying to parse JSON
            if (response.status === 401 || response.status === 403) {
                window.location.href = '/admin/login/';
                return null;
            }
            
            const contentType = response.headers.get('content-type');
            
            // If no content type or not JSON, handle accordingly
            if (!contentType || !contentType.includes('application/json')) {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return null;
            }

            // Try to parse JSON, but handle empty responses
            let data;
            const text = await response.text();
            if (text) {
                try {
                    data = JSON.parse(text);
                } catch (parseError) {
                    // If parsing fails but status is OK, return success
                    if (response.ok) {
                        return { success: true };
                    }
                    throw new Error(`Invalid JSON response: ${response.statusText}`);
                }
            } else {
                // Empty response but status is OK
                if (response.ok) {
                    return { success: true };
                }
                throw new Error(`Empty response: ${response.statusText}`);
            }
            
            if (!response.ok) {
                throw new Error(data.error || data.message || 'API request failed');
            }
            
            return data;
        } catch (error) {
            console.error('API Error:', error);
            showToast('error', error.message || 'An error occurred');
            throw error;
        }
    }

    // Toast notification
    function showToast(type, message) {
        const container = document.getElementById('toast-container');
        if (!container) {
            // Create toast container if it doesn't exist
            const toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
        }
        
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
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    // ==================== STUDENTS ====================

    /**
     * Fetch students list
     */
    async function fetchStudents(page = 1, search = '') {
        const section = document.getElementById('students-section');
        if (!section) return;

        state.students.loading = true;
        showLoadingState('students');

        try {
            const params = new URLSearchParams({
                page: page,
                page_size: 10
            });
            if (search) params.append('search', search);

            const data = await apiCall(`students/?${params.toString()}`);
            
            if (data) {
                state.students.data = data.results;
                state.students.currentPage = data.page;
                state.students.totalPages = data.total_pages;
                renderStudentsTable();
                renderStudentsPagination();
            }
        } catch (error) {
            console.error('Error fetching students:', error);
        } finally {
            state.students.loading = false;
            hideLoadingState('students');
        }
    }

    /**
     * Create new student
     */
    async function createStudent(formData) {
        try {
            const data = await apiCall('students/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            if (data) {
                showToast('success', 'Student created successfully');
                closeModal('student-modal');
                await fetchStudents(state.students.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error creating student:', error);
            throw error;
        }
    }

    /**
     * Update student
     */
    async function updateStudent(id, formData) {
        try {
            const data = await apiCall('students/', {
                method: 'PUT',
                body: JSON.stringify({ id, ...formData })
            });
            
            if (data) {
                showToast('success', 'Student updated successfully');
                closeModal('student-modal');
                await fetchStudents(state.students.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error updating student:', error);
            throw error;
        }
    }

    /**
     * Delete student
     */
    async function deleteStudent(id) {
        if (!confirm('Are you sure you want to delete this student?')) {
            return;
        }

        try {
            // Use the detail endpoint which is more RESTful
            const response = await fetch(buildApiEndpoint(`students/${id}/`), {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken() || '',
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                if (response.status === 404) {
                    const error = await response.json().catch(() => ({ error: 'Student not found' }));
                    throw new Error(error.error || 'Student not found');
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            showToast('success', 'Student deleted successfully');
            await fetchStudents(state.students.currentPage);
        } catch (error) {
            console.error('Error deleting student:', error);
            showToast('error', error.message || 'Failed to delete student');
        }
    }

    /**
     * Update student status (suspend, activate, graduate, defer)
     */
    async function updateStudentStatus(id, status) {
        const statusLabels = {
            'active': 'activate',
            'suspended': 'suspend',
            'graduated': 'graduate',
            'deferred': 'defer'
        };
        const action = statusLabels[status] || status;
        const actionLabel = action.charAt(0).toUpperCase() + action.slice(1);
        
        if (!confirm(`Are you sure you want to ${actionLabel.toLowerCase()} this student?`)) {
            return;
        }

        try {
            const response = await apiCall(`students/${id}/status/`, {
                method: 'PUT',
                body: JSON.stringify({ status })
            });

            if (response) {
                showToast('success', response.message || `Student ${actionLabel.toLowerCase()}d successfully`);
                await fetchStudents(state.students.currentPage);
            }
        } catch (error) {
            console.error(`Error ${action}ing student:`, error);
            // Error already shown by apiCall
        }
    }

    /**
     * Render students table
     */
    function renderStudentsTable() {
        const tbody = document.getElementById('students-tbody');
        if (!tbody) return;

        if (state.students.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-state">
                        <i class="fas fa-user-graduate"></i>
                        <p>No students found</p>
                    </td>
                </tr>
            `;
            return;
        }

        const isAdmin = window.IS_COLLEGE_ADMIN || false;
        
        tbody.innerHTML = state.students.data.map(student => {
            const status = student.status || 'active';
            const statusClass = status === 'active' ? 'badge-success' : 
                              status === 'suspended' ? 'badge-warning' : 
                              status === 'graduated' ? 'badge-info' : 
                              'badge-secondary';
            const statusLabel = status.charAt(0).toUpperCase() + status.slice(1);
            const isSuspended = status === 'suspended';
            
            const studentName = formatToTitleCase(student.full_name);
            const courseName = formatToTitleCase(student.course_name);
            const admissionNumber = (student.admission_number || '').toUpperCase();
            
            return `
            <tr data-id="${student.id}" style="cursor: pointer;" onclick="viewStudentDetails(${student.id}, event)">
                <td>${admissionNumber}</td>
                <td>${studentName}</td>
                <td>${courseName}</td>
                <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                <td class="actions" onclick="event.stopPropagation();">
                    ${isAdmin ? `
                        <button class="btn-icon btn-edit" onclick="editStudent(${student.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${isSuspended ? 
                            `<button class="btn-icon btn-success" onclick="updateStudentStatus(${student.id}, 'active')" title="Activate">
                                <i class="fas fa-check-circle"></i>
                            </button>` :
                            `<button class="btn-icon btn-warning" onclick="updateStudentStatus(${student.id}, 'suspended')" title="Suspend">
                                <i class="fas fa-ban"></i>
                            </button>`
                        }
                        <button class="btn-icon btn-delete" onclick="deleteStudent(${student.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '<span class="text-muted">View only</span>'}
                </td>
            </tr>
        `;
        }).join('');
    }

    /**
     * Render students pagination
     */
    function renderStudentsPagination() {
        const container = document.getElementById('students-pagination');
        if (!container) return;

        if (state.students.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.students.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadStudentsPage(${state.students.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.students.currentPage} of ${state.students.totalPages}</span>`;

        if (state.students.currentPage < state.students.totalPages) {
            html += `<button class="btn-pagination" onclick="loadStudentsPage(${state.students.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== COURSES ====================

    /**
     * Fetch courses list
     */
    async function fetchCourses(page = 1, search = '') {
        const section = document.getElementById('courses-section');
        if (!section) return;

        state.courses.loading = true;
        showLoadingState('courses');

        try {
            const params = new URLSearchParams({
                page: page,
                page_size: 10
            });
            if (search) params.append('search', search);

            const data = await apiCall(`courses/?${params.toString()}`);
            
            if (data) {
                state.courses.data = data.results;
                state.courses.currentPage = data.page;
                state.courses.totalPages = data.total_pages;
                renderCoursesTable();
                renderCoursesPagination();
            }
        } catch (error) {
            console.error('Error fetching courses:', error);
        } finally {
            state.courses.loading = false;
            hideLoadingState('courses');
        }
    }

    /**
     * Create new course
     */
    async function createCourse(formData) {
        try {
            const data = await apiCall('courses/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            if (data) {
                showToast('success', 'Course created successfully');
                closeModal('course-modal');
                await fetchCourses(state.courses.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error creating course:', error);
            throw error;
        }
    }

    /**
     * Update course
     */
    async function updateCourse(id, formData) {
        try {
            const data = await apiCall('courses/', {
                method: 'PUT',
                body: JSON.stringify({ id, ...formData })
            });
            
            if (data) {
                showToast('success', 'Course updated successfully');
                closeModal('course-modal');
                await fetchCourses(state.courses.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error updating course:', error);
            throw error;
        }
    }

    /**
     * Delete course
     */
    async function deleteCourse(id) {
        if (!confirm('Are you sure you want to delete this course?')) {
            return;
        }

        try {
            await apiCall('courses/', {
                method: 'DELETE',
                body: JSON.stringify({ id })
            });
            
            showToast('success', 'Course deleted successfully');
            await fetchCourses(state.courses.currentPage);
        } catch (error) {
            console.error('Error deleting course:', error);
        }
    }

    /**
     * Render courses table
     */
    function renderCoursesTable() {
        const tbody = document.getElementById('courses-tbody');
        if (!tbody) return;

        if (state.courses.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-state">
                        <i class="fas fa-book"></i>
                        <p>No courses found</p>
                    </td>
                </tr>
            `;
            return;
        }

        const isAdmin = window.IS_COLLEGE_ADMIN || false;
        
        tbody.innerHTML = state.courses.data.map(course => `
            <tr data-id="${course.id}">
                <td>${(course.code || '').toUpperCase() || '-'}</td>
                <td>
                    ${course.name || '-'}
                    ${course.global_course_name ? `<span class="badge badge-info" style="margin-left: 8px; font-size: 0.75em;" title="Adapted from: ${course.global_course_name} (${course.global_course_level || ''})">
                        <i class="fas fa-link"></i> ${course.global_course_level || 'Global'}
                    </span>` : ''}
                </td>
                <td>${course.duration || '-'} ${course.duration === 1 ? 'year' : 'years'}</td>
                <td><span class="badge badge-active">${course.status || 'active'}</span></td>
                <td class="actions">
                    ${isAdmin ? `
                        <button class="btn-icon btn-edit" onclick="editCourse(${course.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn-icon btn-delete" onclick="deleteCourse(${course.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '<span class="text-muted">View only</span>'}
                </td>
            </tr>
        `).join('');
    }

    /**
     * Render courses pagination
     */
    function renderCoursesPagination() {
        const container = document.getElementById('courses-pagination');
        if (!container) return;

        if (state.courses.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.courses.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadCoursesPage(${state.courses.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.courses.currentPage} of ${state.courses.totalPages}</span>`;

        if (state.courses.currentPage < state.courses.totalPages) {
            html += `<button class="btn-pagination" onclick="loadCoursesPage(${state.courses.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== UNITS ====================

    let unitsSearchTimeout = null;
    let allLecturersList = [];
    let allCoursesList = [];

    /**
     * Search units with filters (for college admins)
     */
    async function searchUnitsWithFilters() {
        if (unitsSearchTimeout) {
            clearTimeout(unitsSearchTimeout);
        }

        unitsSearchTimeout = setTimeout(async () => {
            const searchInput = document.getElementById('units-search');
            const lecturerFilter = document.getElementById('units-lecturer-filter');
            const semesterFilter = document.getElementById('units-semester-filter');
            const courseFilter = document.getElementById('units-course-filter');
            const resultsContainer = document.getElementById('units-search-results');
            const loadingContainer = document.getElementById('units-search-loading');

            if (!resultsContainer) return;

            const search = searchInput?.value || '';
            const lecturer = lecturerFilter?.value || '';
            const semester = semesterFilter?.value || '';
            const course = courseFilter?.value || '';

            // If only semester filter is set and no other filters, use loadUnitsBySemester
            if (semester && !search && !lecturer && !course) {
                await loadUnitsBySemester(parseInt(semester));
                return;
            }

            // Show loading
            resultsContainer.style.display = 'none';
            if (loadingContainer) loadingContainer.style.display = 'block';

            try {
                const params = new URLSearchParams();
                if (search) params.append('search', search);
                if (lecturer) params.append('lecturer', lecturer);
                if (semester) params.append('semester', semester);
                if (course) params.append('course', course);

                const data = await apiCall(`units/?${params.toString()}`);
                
                if (loadingContainer) loadingContainer.style.display = 'none';
                resultsContainer.style.display = 'block';

                if (data && data.results && data.results.length > 0) {
                    renderUnitsList(data.results);
                } else {
                    resultsContainer.innerHTML = `
                        <div class="empty-state" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
                            <i class="fas fa-search" style="font-size: 48px; margin-bottom: 16px; opacity: 0.3;"></i>
                            <p style="font-size: 16px; margin: 0;">No units found matching your search criteria</p>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('Error searching units:', error);
                if (loadingContainer) loadingContainer.style.display = 'none';
                resultsContainer.style.display = 'block';
                resultsContainer.innerHTML = `
                    <div class="error-message" style="padding: 20px; text-align: center; color: var(--error-color);">
                        <i class="fas fa-exclamation-triangle"></i>
                        Failed to search units. Please try again.
                    </div>
                `;
            }
        }, 500); // Debounce 500ms
    }

    /**
     * Render units search results as cards
     */
    function renderUnitsSearchResults(units) {
        const container = document.getElementById('units-search-results');
        if (!container) return;

        container.innerHTML = `
            <div class="units-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;">
                ${units.map(unit => `
                    <div class="unit-card" onclick="showUnitDetail(${unit.id})" style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; background: white; cursor: pointer; transition: all 0.2s; hover:border-color: #007bff;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                            <div style="flex: 1;">
                                <div style="font-weight: 600; color: #2c3e50; font-size: 16px; margin-bottom: 4px;">${(unit.code || '').toUpperCase()}</div>
                                <div style="font-size: 14px; color: #6c757d; margin-bottom: 8px;">${unit.name}</div>
                                <div style="font-size: 12px; color: #495057; margin-top: 8px;">
                                    <i class="fas fa-calendar-alt" style="margin-right: 4px;"></i>
                                    Semester ${unit.semester}
                                </div>
                                ${unit.lecturer_name ? `
                                    <div style="font-size: 12px; color: #495057; margin-top: 4px;">
                                        <i class="fas fa-chalkboard-teacher" style="margin-right: 4px;"></i>
                                        ${unit.lecturer_name}
                                    </div>
                                ` : '<div style="font-size: 12px; color: #adb5bd; margin-top: 4px;"><i class="fas fa-user-slash" style="margin-right: 4px;"></i>No lecturer assigned</div>'}
                                ${unit.course_assignments && unit.course_assignments.length > 0 ? `
                                    <div style="font-size: 12px; color: #495057; margin-top: 8px; padding-top: 8px; border-top: 1px solid #e0e0e0;">
                                        <i class="fas fa-book" style="margin-right: 4px;"></i>
                                        ${unit.course_assignments.length} course${unit.course_assignments.length !== 1 ? 's' : ''}
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * Show unit detail form in floating dialog
     */
    async function showUnitDetail(unitId) {
        const modal = document.getElementById('unit-detail-modal');
        const detailContent = document.getElementById('unit-detail-content');
        
        if (!modal || !detailContent) return;

        // Show loading
        detailContent.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-color);"><i class="fas fa-spinner fa-spin"></i> Loading unit details...</div>';
        openModal('unit-detail-modal');

        try {
            const data = await apiCall(`units/${unitId}/`);
            
            if (data) {
                renderUnitDetailForm(data);
            } else {
                detailContent.innerHTML = '<div class="error-message" style="color: var(--error-color);">Failed to load unit details</div>';
            }
        } catch (error) {
            console.error('Error loading unit detail:', error);
            detailContent.innerHTML = `
                <div class="error-message" style="padding: 20px; text-align: center; color: var(--error-color);">
                    <i class="fas fa-exclamation-triangle"></i>
                    Failed to load unit details. Please try again.
                </div>
            `;
        }
    }

    /**
     * Close unit detail modal
     */
    function closeUnitDetailModal() {
        closeModal('unit-detail-modal');
    }

    /**
     * Render unit detail form with dark theme
     */
    function renderUnitDetailForm(unit) {
        const detailContent = document.getElementById('unit-detail-content');
        if (!detailContent) return;
        
        // Store unit ID for refresh after update
        detailContent.dataset.unitId = unit.id;

        const isAdmin = window.IS_COLLEGE_ADMIN || false;

        let coursesHtml = '';
        if (unit.course_assignments && unit.course_assignments.length > 0) {
            coursesHtml = `
                <div class="form-group" style="margin-top: 24px;">
                    <label class="form-label" style="font-weight: 600; margin-bottom: 12px; color: var(--text-color);">Course Assignments</label>
                    <div style="display: grid; gap: 12px;">
                        ${unit.course_assignments.map(ca => `
                            <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; border-left: 3px solid var(--primary-color);">
                                <div style="font-weight: 600; color: var(--text-color);">${ca.course_name}</div>
                                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                                    Year ${ca.year} - Semester ${ca.semester}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else {
            coursesHtml = `
                <div class="form-group" style="margin-top: 24px;">
                    <label class="form-label" style="font-weight: 600; margin-bottom: 12px; color: var(--text-color);">Course Assignments</label>
                    <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; color: var(--text-secondary);">
                        No course assignments found
                    </div>
                </div>
            `;
        }

        detailContent.innerHTML = `
            <div style="max-width: 100%;">
                <div class="form-group">
                    <label class="form-label" style="color: var(--text-color);">Unit Code</label>
                    <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; font-weight: 600; color: var(--text-color);">
                        ${(unit.code || '').toUpperCase()}
                    </div>
                </div>
                
                <div class="form-group">
                    <label class="form-label" style="color: var(--text-color);">Unit Name</label>
                    <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; color: var(--text-color);">
                        ${unit.name}
                    </div>
                </div>
                
                <div class="form-row">
                    <div class="form-group">
                        <label class="form-label" style="color: var(--text-color);">Semester</label>
                        <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; color: var(--text-color);">
                            Semester ${unit.semester}
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label" style="color: var(--text-color);">Assigned Lecturer</label>
                        <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; color: var(--text-color);">
                            ${unit.lecturer_name || '<span style="color: var(--text-muted);">Not assigned</span>'}
                        </div>
                    </div>
                </div>
                
                ${unit.global_unit_code ? `
                    <div class="form-group">
                        <label class="form-label" style="color: var(--text-color);">Global Unit Reference</label>
                        <div style="padding: 12px; background: var(--bg-card-hover); border-radius: 6px; color: var(--text-color);">
                            ${unit.global_unit_code} - ${unit.global_unit_name || ''}
                        </div>
                    </div>
                ` : ''}
                
                ${coursesHtml}
                
                ${isAdmin ? `
                    <div class="form-group" style="margin-top: 32px; padding-top: 24px; border-top: 2px solid var(--border-color); display: flex; gap: 8px; justify-content: flex-end;">
                        <button class="btn btn-primary" onclick="editUnitFromDetail(${unit.id})" style="padding: 8px 16px; font-size: 14px; min-width: auto;">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        <button class="btn btn-danger" onclick="deleteUnitFromDetail(${unit.id})" style="padding: 8px 16px; font-size: 14px; min-width: auto;">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                ` : ''}
            </div>
        `;
    }

    /**
     * Close unit detail form (kept for backward compatibility)
     */
    function closeUnitDetail() {
        closeUnitDetailModal();
    }

    /**
     * Edit unit from detail form
     */
    function editUnitFromDetail(unitId) {
        closeUnitDetailModal();
        // Use existing editUnit function
        if (typeof window.editUnit === 'function') {
            window.editUnit(unitId);
        }
    }

    /**
     * Delete unit from detail form
     */
    async function deleteUnitFromDetail(unitId) {
        if (!confirm('Are you sure you want to delete this unit? This action cannot be undone.')) {
            return;
        }

        try {
            await apiCall('units/', {
                method: 'DELETE',
                body: JSON.stringify({ id: unitId })
            });
            
            showToast('success', 'Unit deleted successfully');
            closeUnitDetailModal();
            
            // Refresh units list - check if semester filter is set, otherwise load semester 1
            if (window.IS_COLLEGE_ADMIN) {
                const semesterFilter = document.getElementById('units-semester-filter');
                const semester = semesterFilter?.value || '1';
                if (semester) {
                    await loadUnitsBySemester(parseInt(semester));
                } else {
                    await loadUnitsBySemester(1);
                }
            } else {
                // Refresh lecturer units if on lecturer view
                loadLecturerUnits();
            }
        } catch (error) {
            console.error('Error deleting unit:', error);
            showToast('error', 'Failed to delete unit');
        }
    }

    /**
     * Load lecturer's units (for lecturers only)
     */
    async function loadLecturerUnits() {
        const container = document.getElementById('my-units-container');
        if (!container) return;

        container.innerHTML = '<div class="loading-state"><i class="fas fa-spinner fa-spin"></i> Loading your units...</div>';

        try {
            const data = await apiCall('units/my-units/');
            
            if (data && data.results && data.results.length > 0) {
                container.innerHTML = `
                    <div class="units-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;">
                        ${data.results.map(unit => `
                            <div class="unit-card" onclick="showUnitDetail(${unit.id})" style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; background: white; cursor: pointer; transition: all 0.2s;">
                                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600; color: #2c3e50; font-size: 16px; margin-bottom: 4px;">${(unit.code || '').toUpperCase()}</div>
                                        <div style="font-size: 14px; color: #6c757d; margin-bottom: 8px;">${unit.name}</div>
                                        <div style="font-size: 12px; color: #495057; margin-top: 8px;">
                                            <i class="fas fa-calendar-alt" style="margin-right: 4px;"></i>
                                            Semester ${unit.semester}
                                        </div>
                                        ${unit.course_assignments && unit.course_assignments.length > 0 ? `
                                            <div style="font-size: 12px; color: #495057; margin-top: 8px; padding-top: 8px; border-top: 1px solid #e0e0e0;">
                                                <i class="fas fa-book" style="margin-right: 4px;"></i>
                                                Assigned to ${unit.course_assignments.length} course${unit.course_assignments.length !== 1 ? 's' : ''}
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            } else {
                container.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 60px 20px; color: #6c757d;">
                        <i class="fas fa-book-open" style="font-size: 48px; margin-bottom: 16px; opacity: 0.3;"></i>
                        <p style="font-size: 16px; margin: 0;">No units assigned to you yet</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading lecturer units:', error);
            container.innerHTML = `
                <div class="error-message" style="padding: 20px; text-align: center; color: #dc3545;">
                    <i class="fas fa-exclamation-triangle"></i>
                    Failed to load your units. Please try again.
                </div>
            `;
        }
    }

    /**
     * Initialize units section - load filters and lecturer units
     */
    async function initializeUnitsSection() {
        // Load lecturers and courses for filters (admin only)
        if (window.IS_COLLEGE_ADMIN) {
            await loadUnitsFilters();
            // Load semester 1 units by default
            await loadUnitsBySemester(1);
        }
        
        // Load lecturer units (lecturer only)
        if (window.USER_ROLE === 'lecturer') {
            await loadLecturerUnits();
        }
    }

    /**
     * Load units by semester (default: semester 1)
     */
    async function loadUnitsBySemester(semester = 1) {
        const resultsContainer = document.getElementById('units-search-results');
        const loadingContainer = document.getElementById('units-search-loading');
        
        if (!resultsContainer) return;

        // Show loading
        resultsContainer.style.display = 'none';
        if (loadingContainer) loadingContainer.style.display = 'block';

        try {
            const params = new URLSearchParams();
            params.append('semester', semester);
            
            const data = await apiCall(`units/?${params.toString()}`);
            
            if (loadingContainer) loadingContainer.style.display = 'none';
            resultsContainer.style.display = 'block';

            if (data && data.results && data.results.length > 0) {
                renderUnitsList(data.results);
            } else {
                resultsContainer.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 60px 20px; color: var(--text-secondary);">
                        <i class="fas fa-book-open" style="font-size: 48px; margin-bottom: 16px; opacity: 0.3;"></i>
                        <p style="font-size: 16px; margin: 0;">No units found for Semester ${semester}</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading units:', error);
            if (loadingContainer) loadingContainer.style.display = 'none';
            resultsContainer.style.display = 'block';
            resultsContainer.innerHTML = `
                <div class="error-message" style="padding: 20px; text-align: center; color: #dc3545;">
                    <i class="fas fa-exclamation-triangle"></i>
                    Failed to load units. Please try again.
                </div>
            `;
        }
    }

    /**
     * Render units list as cards
     */
    function renderUnitsList(units) {
        const container = document.getElementById('units-search-results');
        if (!container) return;

        container.innerHTML = `
            <div class="units-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px;">
                ${units.map(unit => `
                    <div class="unit-card" onclick="showUnitDetail(${unit.id})" style="border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; background: var(--bg-card); cursor: pointer; transition: all 0.2s; hover:border-color: var(--primary-color); hover:box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
                            <div style="flex: 1;">
                                <div style="font-weight: 600; color: var(--text-color); font-size: 16px; margin-bottom: 4px;">${(unit.code || '').toUpperCase()}</div>
                                <div style="font-size: 14px; color: var(--text-secondary); margin-bottom: 8px;">${unit.name}</div>
                                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">
                                    <i class="fas fa-calendar-alt" style="margin-right: 4px;"></i>
                                    Semester ${unit.semester}
                                </div>
                                ${unit.lecturer_name ? `
                                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
                                        <i class="fas fa-chalkboard-teacher" style="margin-right: 4px;"></i>
                                        ${unit.lecturer_name}
                                    </div>
                                ` : '<div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;"><i class="fas fa-user-slash" style="margin-right: 4px;"></i>No lecturer assigned</div>'}
                                ${unit.course_assignments && unit.course_assignments.length > 0 ? `
                                    <div style="font-size: 12px; color: var(--text-secondary); margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border-color);">
                                        <i class="fas fa-book" style="margin-right: 4px;"></i>
                                        ${unit.course_assignments.length} course${unit.course_assignments.length !== 1 ? 's' : ''}
                                    </div>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }

    /**
     * Load filters for units search
     */
    async function loadUnitsFilters() {
        try {
            // Load lecturers
            const lecturersData = await apiCall('lecturers/');
            if (lecturersData && lecturersData.results) {
                allLecturersList = lecturersData.results;
                const lecturerFilter = document.getElementById('units-lecturer-filter');
                if (lecturerFilter) {
                    lecturerFilter.innerHTML = '<option value="">All Lecturers</option>';
                    allLecturersList.forEach(lecturer => {
                        lecturerFilter.innerHTML += `<option value="${lecturer.id}">${lecturer.full_name || lecturer.name}</option>`;
                    });
                }
            }

            // Load courses
            const coursesData = await apiCall('courses/');
            if (coursesData && coursesData.results) {
                allCoursesList = coursesData.results;
                const courseFilter = document.getElementById('units-course-filter');
                if (courseFilter) {
                    courseFilter.innerHTML = '<option value="">All Courses</option>';
                    allCoursesList.forEach(course => {
                        courseFilter.innerHTML += `<option value="${course.id}">${course.name}</option>`;
                    });
                }
            }

            // Set semester filter to 1 by default
            const semesterFilter = document.getElementById('units-semester-filter');
            if (semesterFilter) {
                // Populate semester options if not already populated
                if (semesterFilter.options.length <= 1) {
                    const maxSemesters = 12; // Adjust based on your college's max semesters
                    for (let i = 1; i <= maxSemesters; i++) {
                        const option = document.createElement('option');
                        option.value = i;
                        option.textContent = `Semester ${i}`;
                        semesterFilter.appendChild(option);
                    }
                }
                // Set default to semester 1
                semesterFilter.value = '1';
            }
        } catch (error) {
            console.error('Error loading units filters:', error);
        }
    }

    /**
     * Create new unit
     */
    async function createUnit(formData) {
        try {
            const data = await apiCall('units/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            if (data) {
                showToast('success', 'Unit created successfully');
                closeModal('unit-modal');
                // Refresh units list - check if semester filter is set, otherwise load semester 1
                if (window.IS_COLLEGE_ADMIN) {
                    const semesterFilter = document.getElementById('units-semester-filter');
                    const semester = semesterFilter?.value || formData.semester || '1';
                    if (semester) {
                        await loadUnitsBySemester(parseInt(semester));
                    } else {
                        await loadUnitsBySemester(1);
                    }
                } else if (window.USER_ROLE === 'lecturer' && typeof loadLecturerUnits === 'function') {
                    await loadLecturerUnits();
                }
                return data;
            }
        } catch (error) {
            console.error('Error creating unit:', error);
            throw error;
        }
    }

    /**
     * Update unit
     */
    async function updateUnit(id, formData) {
        try {
            const data = await apiCall('units/', {
                method: 'PUT',
                body: JSON.stringify({ id, ...formData })
            });
            
            if (data) {
                showToast('success', 'Unit updated successfully');
                closeModal('unit-modal');
                // Refresh units list - check if semester filter is set, otherwise load semester 1
                if (window.IS_COLLEGE_ADMIN) {
                    const semesterFilter = document.getElementById('units-semester-filter');
                    const semester = semesterFilter?.value || formData.semester || '1';
                    if (semester) {
                        await loadUnitsBySemester(parseInt(semester));
                    } else {
                        await loadUnitsBySemester(1);
                    }
                } else if (window.USER_ROLE === 'lecturer' && typeof loadLecturerUnits === 'function') {
                    await loadLecturerUnits();
                }
                // Also refresh unit detail modal if it's open
                const modal = document.getElementById('unit-detail-modal');
                if (modal && modal.style.display !== 'none') {
                    const detailContent = document.getElementById('unit-detail-content');
                    if (detailContent && detailContent.dataset.unitId) {
                        await showUnitDetail(parseInt(detailContent.dataset.unitId));
                    }
                }
                return data;
            }
        } catch (error) {
            console.error('Error updating unit:', error);
            throw error;
        }
    }

    /**
     * Delete unit
     */
    async function deleteUnit(id) {
        if (!confirm('Are you sure you want to delete this unit?')) {
            return;
        }

        try {
            await apiCall('units/', {
                method: 'DELETE',
                body: JSON.stringify({ id })
            });
            
            showToast('success', 'Unit deleted successfully');
            // Reload units using searchUnitsWithFilters
            if (typeof searchUnitsWithFilters === 'function') {
                await searchUnitsWithFilters();
            }
        } catch (error) {
            console.error('Error deleting unit:', error);
        }
    }

    /**
     * Render units table
     */
    function renderUnitsTable() {
        const tbody = document.getElementById('units-tbody');
        if (!tbody) return;

        if (state.units.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" class="empty-state">
                        <i class="fas fa-book-open"></i>
                        <p>No units found</p>
                    </td>
                </tr>
            `;
            return;
        }

        const isAdmin = window.IS_COLLEGE_ADMIN || false;
        
        tbody.innerHTML = state.units.data.map(unit => `
            <tr data-id="${unit.id}">
                <td>${(unit.code || '').toUpperCase() || '-'}</td>
                <td>
                    ${unit.name || '-'}
                    ${unit.global_unit_code ? `<span class="badge badge-info" style="margin-left: 8px; font-size: 0.75em;" title="Adapted from: ${(unit.global_unit_code || '').toUpperCase()} - ${unit.global_unit_name || ''}">
                        <i class="fas fa-link"></i> ${(unit.global_unit_code || '').toUpperCase()}
                    </span>` : ''}
                </td>
                <td>Semester ${unit.semester || '-'}</td>
                <td>${unit.lecturer_name || 'Not assigned'}</td>
                <td class="actions">
                    ${isAdmin ? `
                        <button class="btn-icon btn-edit" onclick="editUnit(${unit.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn-icon btn-delete" onclick="deleteUnit(${unit.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '<span class="text-muted">View only</span>'}
                </td>
            </tr>
        `).join('');
    }

    /**
     * Render units pagination
     */
    function renderUnitsPagination() {
        const container = document.getElementById('units-pagination');
        if (!container) return;

        if (state.units.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.units.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadUnitsPage(${state.units.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.units.currentPage} of ${state.units.totalPages}</span>`;

        if (state.units.currentPage < state.units.totalPages) {
            html += `<button class="btn-pagination" onclick="loadUnitsPage(${state.units.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== DEPARTMENTS ====================

    async function fetchDepartments(page = 1, search = '', skipSectionCheck = false) {
        const section = document.getElementById('departments-section');
        if (!section && !skipSectionCheck) return;

        if (section) {
            state.departments.loading = true;
            showLoadingState('departments');
        }

        try {
            const params = new URLSearchParams({
                page: page,
                page_size: 100,  // Get more departments for dropdown (increased from 10)
                include_courses: 'true'  // Include courses in response
            });
            if (search) params.append('search', search);

            const data = await apiCall(`departments/?${params.toString()}`);
            
            if (data) {
                state.departments.data = data.results;
                state.departments.currentPage = data.page;
                state.departments.totalPages = data.total_pages;
                
                // Only render if section exists
                if (section) {
                    renderDepartmentsTable();
                    renderDepartmentsPagination();
                }
                
                // Return data for use in dropdowns
                return data;
            }
        } catch (error) {
            console.error('Error fetching departments:', error);
            throw error;  // Re-throw so callers can handle it
        } finally {
            if (section) {
                state.departments.loading = false;
                hideLoadingState('departments');
            }
        }
    }

    async function createDepartment(formData) {
        try {
            const data = await apiCall('departments/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            if (data) {
                showToast('success', 'Department created successfully');
                closeModal('department-modal');
                await fetchDepartments(state.departments.currentPage);
                return data;
            } else {
                throw new Error('No data returned from server');
            }
        } catch (error) {
            console.error('Error creating department:', error);
            const errorMsg = error.message || 'Failed to create department. Please try again.';
            showToast('error', errorMsg);
            throw error;
        }
    }

    async function updateDepartment(id, formData) {
        try {
            const data = await apiCall('departments/', {
                method: 'PUT',
                body: JSON.stringify({ id, ...formData })
            });
            
            if (data) {
                showToast('success', 'Department updated successfully');
                closeModal('department-modal');
                await fetchDepartments(state.departments.currentPage);
                return data;
            } else {
                throw new Error('No data returned from server');
            }
        } catch (error) {
            console.error('Error updating department:', error);
            const errorMsg = error.message || 'Failed to update department. Please try again.';
            showToast('error', errorMsg);
            throw error;
        }
    }

    async function deleteDepartment(id) {
        if (!confirm('Are you sure you want to delete this department?')) {
            return;
        }

        try {
            // Get the department to find its name for deletion
            const dept = state.departments.data.find(d => d.id === id);
            const oldName = dept ? dept.name : null;
            
            await apiCall('departments/', {
                method: 'DELETE',
                body: JSON.stringify({ id, old_name: oldName })
            });
            
            showToast('success', 'Department deleted successfully');
            await fetchDepartments(state.departments.currentPage);
        } catch (error) {
            console.error('Error deleting department:', error);
            const errorMsg = error.message || 'Failed to delete department. Please try again.';
            showToast('error', errorMsg);
        }
    }

    function renderDepartmentsTable() {
        const tbody = document.getElementById('departments-tbody');
        if (!tbody) return;

        if (state.departments.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" class="empty-state">
                        <i class="fas fa-building"></i>
                        <p>No departments found</p>
                    </td>
                </tr>
            `;
            return;
        }

        const isAdmin = window.IS_COLLEGE_ADMIN || false;
        
        // Render as expandable cards
        tbody.innerHTML = state.departments.data.map(dept => {
            const isExpanded = state.departments.expandedDepartments.has(dept.id);
            const courses = dept.courses || [];
            const courseCount = dept.course_count || courses.length || 0;
            
            return `
                <tr class="department-row" data-id="${dept.id}">
                    <td colspan="4" style="padding: 0; border: none;">
                        <div class="department-card">
                            <div class="department-header" onclick="toggleDepartment(${dept.id})">
                                <i class="fas fa-chevron-${isExpanded ? 'down' : 'right'}"></i>
                                <div style="flex: 1; display: flex; align-items: center; gap: 12px;">
                                    <strong style="color: var(--text-color, #1f2937);">${dept.code || '-'}</strong>
                                    <span style="color: var(--text-color, #1f2937);">${dept.name || '-'}</span>
                                    <span class="badge badge-info" style="font-size: 0.75em; padding: 4px 8px;">
                                        ${courseCount} ${courseCount === 1 ? 'course' : 'courses'}
                                    </span>
                                </div>
                                <div class="department-actions" onclick="event.stopPropagation();">
                                    ${isAdmin ? `
                                        <button class="btn-icon btn-edit" onclick="editDepartment(${dept.id})" title="Edit">
                                            <i class="fas fa-edit"></i>
                                        </button>
                                        <button class="btn-icon btn-delete" onclick="deleteDepartment(${dept.id})" title="Delete">
                                            <i class="fas fa-trash"></i>
                                        </button>
                                    ` : '<span class="text-muted" style="font-size: 0.875em;">View only</span>'}
                                </div>
                            </div>
                            ${isExpanded ? `
                                <div class="department-courses">
                                    ${dept.description ? `<p style="margin: 0 0 16px 0; color: var(--text-light, #6b7280); font-size: 0.875em;">${dept.description}</p>` : ''}
                                    ${courses.length > 0 ? `
                                        <div style="overflow-x: auto;">
                                            <table>
                                                <thead>
                                                    <tr>
                                                        <th>Code</th>
                                                        <th>Name</th>
                                                        <th>Duration</th>
                                                        <th>Status</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    ${courses.map(course => `
                                                        <tr>
                                                            <td>${(course.code || '').toUpperCase() || '-'}</td>
                                                            <td>
                                                                ${course.name || '-'}
                                                                ${course.global_course_name ? `
                                                                    <span class="badge badge-info" style="margin-left: 8px; font-size: 0.75em;" title="Adapted from: ${course.global_course_name} (${course.global_course_level || ''})">
                                                                        <i class="fas fa-link"></i> ${course.global_course_level || 'Global'}
                                                                    </span>
                                                                ` : ''}
                                                            </td>
                                                            <td>${course.duration || '-'} ${course.duration === 1 ? 'year' : 'years'}</td>
                                                            <td>
                                                                <span class="badge badge-active">${course.status || 'active'}</span>
                                                            </td>
                                                        </tr>
                                                    `).join('')}
                                                </tbody>
                                            </table>
                                        </div>
                                    ` : `
                                        <div style="text-align: center; padding: 20px; color: var(--text-light, #6b7280);">
                                            <i class="fas fa-book" style="font-size: 2em; margin-bottom: 8px; opacity: 0.5;"></i>
                                            <p style="margin: 0;">No courses in this department</p>
                                        </div>
                                    `}
                                </div>
                            ` : ''}
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }

    // Toggle department expand/collapse
    window.toggleDepartment = function(deptId) {
        if (state.departments.expandedDepartments.has(deptId)) {
            state.departments.expandedDepartments.delete(deptId);
        } else {
            state.departments.expandedDepartments.add(deptId);
        }
        renderDepartmentsTable();
    };

    function renderDepartmentsPagination() {
        const container = document.getElementById('departments-pagination');
        if (!container) return;

        if (state.departments.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.departments.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadDepartmentsPage(${state.departments.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.departments.currentPage} of ${state.departments.totalPages}</span>`;

        if (state.departments.currentPage < state.departments.totalPages) {
            html += `<button class="btn-pagination" onclick="loadDepartmentsPage(${state.departments.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== LECTURERS ====================

    async function fetchLecturers(page = 1, search = '') {
        const section = document.getElementById('lecturers-section');
        if (!section) return;

        state.lecturers.loading = true;
        showLoadingState('lecturers');

        try {
            const params = new URLSearchParams({
                page: page,
                page_size: 10
            });
            if (search) params.append('search', search);

            const data = await apiCall(`lecturers/?${params.toString()}`);
            
            if (data) {
                state.lecturers.data = data.results;
                state.lecturers.currentPage = data.page;
                state.lecturers.totalPages = data.total_pages;
                renderLecturersTable();
                renderLecturersPagination();
            }
        } catch (error) {
            console.error('Error fetching lecturers:', error);
        } finally {
            state.lecturers.loading = false;
            hideLoadingState('lecturers');
        }
    }

    async function createLecturer(formData) {
        try {
            const data = await apiCall('lecturers/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            if (data) {
                showToast('success', 'Lecturer created successfully');
                closeModal('lecturer-modal');
                await fetchLecturers(state.lecturers.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error creating lecturer:', error);
            throw error;
        }
    }

    async function updateLecturer(id, formData) {
        try {
            const data = await apiCall('lecturers/', {
                method: 'PUT',
                body: JSON.stringify({ id, ...formData })
            });
            
            if (data) {
                // Don't show toast or close modal here - let the caller handle it
                // This allows handleLecturerSubmit to show custom messages
                await fetchLecturers(state.lecturers.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error updating lecturer:', error);
            throw error;
        }
    }

    async function deleteLecturer(id) {
        if (!confirm('Are you sure you want to delete this lecturer?')) {
            return;
        }

        try {
            // Use the detail endpoint which is more RESTful
            const response = await fetch(buildApiEndpoint(`lecturers/${id}/`), {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken() || '',
                },
                credentials: 'same-origin'
            });

            if (!response.ok) {
                if (response.status === 404) {
                    const error = await response.json().catch(() => ({ error: 'Lecturer not found' }));
                    throw new Error(error.error || 'Lecturer not found');
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            showToast('success', 'Lecturer deleted successfully');
            await fetchLecturers(state.lecturers.currentPage);
        } catch (error) {
            console.error('Error deleting lecturer:', error);
            showToast('error', error.message || 'Failed to delete lecturer');
        }
    }

    /**
     * Update lecturer status (suspend or activate)
     */
    async function updateLecturerStatus(id, action) {
        const actionLabel = action.charAt(0).toUpperCase() + action.slice(1);
        
        if (!confirm(`Are you sure you want to ${actionLabel.toLowerCase()} this lecturer?`)) {
            return;
        }

        try {
            const response = await apiCall(`lecturers/${id}/status/`, {
                method: 'PUT',
                body: JSON.stringify({ action })
            });

            if (response) {
                showToast('success', response.message || `Lecturer ${actionLabel.toLowerCase()}d successfully`);
                await fetchLecturers(state.lecturers.currentPage);
            }
        } catch (error) {
            console.error(`Error ${action}ing lecturer:`, error);
            // Error already shown by apiCall
        }
    }

    function renderLecturersTable() {
        const tbody = document.getElementById('lecturers-tbody');
        if (!tbody) return;

        if (state.lecturers.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="empty-state">
                        <i class="fas fa-chalkboard-teacher"></i>
                        <p>No lecturers found</p>
                    </td>
                </tr>
            `;
            return;
        }

        const isAdmin = window.IS_COLLEGE_ADMIN || false;
        
        tbody.innerHTML = state.lecturers.data.map(lecturer => {
            const isActive = lecturer.is_active !== false; // Default to true if not specified
            const statusClass = isActive ? 'badge-success' : 'badge-warning';
            const statusLabel = isActive ? 'Active' : 'Suspended';
            
            return `
            <tr data-id="${lecturer.id}">
                <td>${lecturer.full_name || '-'}</td>
                <td>${lecturer.email || '-'}</td>
                <td>${lecturer.phone || '-'}</td>
                <td>${lecturer.assigned_units_count || 0}</td>
                <td><span class="badge ${statusClass}">${statusLabel}</span></td>
                <td class="actions">
                    ${isAdmin ? `
                        <button class="btn-icon btn-edit" onclick="editLecturer(${lecturer.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        ${isActive ? 
                            `<button class="btn-icon btn-warning" onclick="updateLecturerStatus(${lecturer.id}, 'suspend')" title="Suspend">
                                <i class="fas fa-ban"></i>
                            </button>` :
                            `<button class="btn-icon btn-success" onclick="updateLecturerStatus(${lecturer.id}, 'activate')" title="Activate">
                                <i class="fas fa-check-circle"></i>
                            </button>`
                        }
                        <button class="btn-icon btn-delete" onclick="deleteLecturer(${lecturer.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : '<span class="text-muted">View only</span>'}
                </td>
            </tr>
        `;
        }).join('');
    }

    function renderLecturersPagination() {
        const container = document.getElementById('lecturers-pagination');
        if (!container) return;

        if (state.lecturers.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.lecturers.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadLecturersPage(${state.lecturers.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.lecturers.currentPage} of ${state.lecturers.totalPages}</span>`;

        if (state.lecturers.currentPage < state.lecturers.totalPages) {
            html += `<button class="btn-pagination" onclick="loadLecturersPage(${state.lecturers.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== ENROLLMENTS ====================

    async function fetchEnrollments(page = 1, search = '', filters = {}) {
        const section = document.getElementById('enrollments-tab-content');
        if (!section) return;

        state.enrollments.loading = true;
        showLoadingState('enrollments');

        try {
            const params = new URLSearchParams({
                page: page,
                page_size: 50
            });
            if (search) params.append('search', search);
            if (filters.unit) params.append('unit', filters.unit);
            if (filters.course) params.append('course', filters.course);
            if (filters.academic_year) params.append('academic_year', filters.academic_year);
            if (filters.semester) params.append('semester', filters.semester);
            if (filters.exam_registered) {
                params.append('exam_registered', filters.exam_registered);
            }

            const data = await apiCall(`enrollments/?${params.toString()}`);
            
            // Always clear loading state and render, even if data is empty
            state.enrollments.loading = false;
            hideLoadingState('enrollments');
            
            if (data && data.results !== undefined) {
                state.enrollments.data = data.results || [];
                state.enrollments.currentPage = data.page || 1;
                state.enrollments.totalPages = data.total_pages || 1;
                state.enrollments.totalCount = data.count || data.results.length || 0;
                renderEnrollmentsTable();
                renderEnrollmentsPagination();
                
                // Update results count
                const countElement = document.getElementById('enrollments-count-text');
                if (countElement) {
                    countElement.textContent = `Showing ${state.enrollments.data.length} of ${state.enrollments.totalCount} enrollments`;
                }
            } else {
                // Handle empty or invalid response
                state.enrollments.data = [];
                state.enrollments.currentPage = 1;
                state.enrollments.totalPages = 1;
                state.enrollments.totalCount = 0;
                renderEnrollmentsTable();
                renderEnrollmentsPagination();
                
                // Update results count
                const countElement = document.getElementById('enrollments-count-text');
                if (countElement) {
                    countElement.textContent = 'No enrollments found';
                }
                
                if (data === null || data === undefined) {
                    console.warn('Enrollments API returned null or undefined');
                } else {
                    console.warn('Enrollments API returned invalid data structure:', data);
                }
            }
        } catch (error) {
            console.error('Error fetching enrollments:', error);
            // Always clear loading state on error
            state.enrollments.loading = false;
            hideLoadingState('enrollments');
            
            // Show error message to user
            const tbody = document.getElementById('enrollments-tbody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" class="error-row">
                            <i class="fas fa-exclamation-triangle"></i>
                            Failed to load enrollments. Please try again.
                            <br><small>${error.message || 'Unknown error'}</small>
                        </td>
                    </tr>
                `;
            }
            
            // Reset state
            state.enrollments.data = [];
            state.enrollments.currentPage = 1;
            state.enrollments.totalPages = 1;
            state.enrollments.totalCount = 0;
            renderEnrollmentsPagination();
            
            // Update results count
            const countElement = document.getElementById('enrollments-count-text');
            if (countElement) {
                countElement.textContent = 'Error loading enrollments';
            }
        }
    }

    async function createEnrollment(formData) {
        try {
            const data = await apiCall('enrollments/', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            
            if (data) {
                showToast('success', 'Student enrolled successfully');
                closeModal('enrollment-modal');
                await fetchEnrollments(state.enrollments.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error creating enrollment:', error);
            throw error;
        }
    }

    async function updateEnrollment(id, formData) {
        try {
            const data = await apiCall('enrollments/', {
                method: 'PUT',
                body: JSON.stringify({ id, ...formData })
            });
            
            if (data) {
                showToast('success', 'Enrollment updated successfully');
                closeModal('enrollment-modal');
                await fetchEnrollments(state.enrollments.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error updating enrollment:', error);
            throw error;
        }
    }

    async function deleteEnrollment(id) {
        if (!confirm('Are you sure you want to delete this enrollment?')) {
            return;
        }

        try {
            await apiCall('enrollments/', {
                method: 'DELETE',
                body: JSON.stringify({ id })
            });
            
            showToast('success', 'Enrollment deleted successfully');
            await fetchEnrollments(state.enrollments.currentPage);
        } catch (error) {
            console.error('Error deleting enrollment:', error);
        }
    }

    function renderEnrollmentsTable() {
        const tbody = document.getElementById('enrollments-tbody');
        if (!tbody) return;

            if (state.enrollments.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" class="empty-state">
                        <i class="fas fa-user-graduate"></i>
                        <p>no enrolment</p>
                        <small style="margin-top: 8px; display: block;">Try adjusting your filters or <a href="#" onclick="clearEnrollmentFilters(); return false;" style="color: #007bff;">clear all filters</a></small>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = state.enrollments.data.map(enrollment => {
            const examStatus = enrollment.exam_registered ? 
                '<span class="badge badge-success"><i class="fas fa-check-circle"></i> Registered</span>' : 
                '<span class="badge badge-secondary"><i class="fas fa-times-circle"></i> Not Registered</span>';
            
            // Format names to proper case
            const studentName = formatToTitleCase(enrollment.student_name);
            const unitName = formatToTitleCase(enrollment.unit_name);
            const unitCode = (enrollment.unit_code || '').toUpperCase();
            const studentAdmission = (enrollment.student_admission || '').toUpperCase();
            
            return `
            <tr data-id="${enrollment.id}">
                <td><strong>${studentName}</strong><br><small style="color: #6c757d;">${studentAdmission}</small></td>
                <td><strong>${unitCode || '-'}</strong><br><small style="color: #6c757d;">${unitName}</small></td>
                <td>${examStatus}</td>
                <td class="actions">
                    <button class="btn-icon btn-edit" onclick="editEnrollment(${enrollment.id})" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn-icon btn-delete" onclick="deleteEnrollment(${enrollment.id})" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `;
        }).join('');
        
        // Update results count
        const countElement = document.getElementById('enrollments-count-text');
        if (countElement) {
            const count = state.enrollments.totalCount || state.enrollments.data.length || 0;
            countElement.textContent = `${count} enrollment${count !== 1 ? 's' : ''} found`;
        }
    }

    function renderEnrollmentsPagination() {
        const container = document.getElementById('enrollments-pagination');
        if (!container) return;

        if (state.enrollments.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.enrollments.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadEnrollmentsPage(${state.enrollments.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.enrollments.currentPage} of ${state.enrollments.totalPages}</span>`;

        if (state.enrollments.currentPage < state.enrollments.totalPages) {
            html += `<button class="btn-pagination" onclick="loadEnrollmentsPage(${state.enrollments.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== RESULTS ====================

    // Flag to prevent concurrent calls
    let isFetchingResults = false;

    async function fetchResults(page = 1, search = '', filters = {}) {
        // Check for the correct element (results-tab-content instead of results-section)
        const section = document.getElementById('results-tab-content');
        if (!section || !section.classList.contains('active')) {
            return; // Don't fetch if tab is not active
        }

        // Prevent concurrent calls
        if (isFetchingResults) {
            console.log('Results fetch already in progress, skipping...');
            return;
        }

        isFetchingResults = true;
        state.results.loading = true;
        showLoadingState('results');

        try {
            const params = new URLSearchParams({
                page: page,
                page_size: 10
            });
            if (search) params.append('search', search);
            if (filters.unit) params.append('unit', filters.unit);
            if (filters.academic_year) params.append('academic_year', filters.academic_year);
            if (filters.semester) params.append('semester', filters.semester);
            if (filters.show_submitted !== undefined) {
                params.append('show_submitted', filters.show_submitted);
            }

            const data = await apiCall(`results/?${params.toString()}`);
            
            // Always clear loading state and render, even if data is empty
            state.results.loading = false;
            isFetchingResults = false;
            hideLoadingState('results');
            
            if (data && data.results !== undefined) {
                state.results.data = data.results || [];
                state.results.currentPage = data.page || 1;
                state.results.totalPages = data.total_pages || 1;
                renderResultsTable();
                renderResultsPagination();
            } else {
                // Handle empty or invalid response
                state.results.data = [];
                state.results.currentPage = 1;
                state.results.totalPages = 1;
                renderResultsTable();
                renderResultsPagination();
                console.warn('Results API returned invalid or empty data');
            }
        } catch (error) {
            console.error('Error fetching results:', error);
            // Always clear loading state on error
            state.results.loading = false;
            isFetchingResults = false;
            hideLoadingState('results');
            
            // Show error message to user
            const tbody = document.getElementById('results-tbody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="error-row">
                            <i class="fas fa-exclamation-triangle"></i>
                            Failed to load results. Please try again.
                            <br><small>${error.message || 'Unknown error'}</small>
                        </td>
                    </tr>
                `;
            }
            
            // Reset state
            state.results.data = [];
            state.results.currentPage = 1;
            state.results.totalPages = 1;
            renderResultsPagination();
        }
    }

    async function saveResult(enrollmentId, formData) {
        try {
            const data = await apiCall('results/', {
                method: 'POST',
                body: JSON.stringify({ enrollment_id: enrollmentId, ...formData })
            });
            
            if (data) {
                showToast('success', 'Result saved successfully');
                closeModal('result-modal');
                await fetchResults(state.results.currentPage);
                return data;
            }
        } catch (error) {
            console.error('Error saving result:', error);
            throw error;
        }
    }

    function renderResultsTable() {
        const tbody = document.getElementById('results-tbody');
        if (!tbody) return;

        if (state.results.data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8" class="empty-state">
                        <i class="fas fa-clipboard-check"></i>
                        <p>No results found</p>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = state.results.data.map(result => {
            const statusBadge = result.status === 'submitted' 
                ? '<span class="badge badge-success">Submitted</span>'
                : '<span class="badge badge-warning">Draft</span>';
            
            const editButton = result.can_edit
                ? `<button class="btn-icon btn-edit" onclick="editResult(${result.enrollment_id})" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>`
                : '<span class="text-muted" title="Cannot edit submitted result">-</span>';
            
            const studentName = formatToTitleCase(result.student_name);
            const unitName = formatToTitleCase(result.unit_name);
            const unitCode = (result.unit_code || '').toUpperCase();
            const studentAdmission = (result.student_admission || '').toUpperCase();
            
            return `
            <tr data-id="${result.id || ''}">
                <td>${studentName} (${studentAdmission})</td>
                <td>${unitCode} - ${unitName}</td>
                <td>${result.cat_marks !== null ? result.cat_marks.toFixed(1) : '-'}</td>
                <td>${result.exam_marks !== null ? result.exam_marks.toFixed(1) : '-'}</td>
                <td>${result.total !== null ? result.total.toFixed(1) : '-'}</td>
                <td><span class="badge badge-grade-${result.grade || 'N/A'}">${result.grade || 'N/A'}</span></td>
                <td>${statusBadge}</td>
                <td class="actions">${editButton}</td>
            </tr>
        `;
        }).join('');
    }

    function renderResultsPagination() {
        const container = document.getElementById('results-pagination');
        if (!container) return;

        if (state.results.totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = '';
        if (state.results.currentPage > 1) {
            html += `<button class="btn-pagination" onclick="loadResultsPage(${state.results.currentPage - 1})">
                <i class="fas fa-chevron-left"></i> Previous
            </button>`;
        }

        html += `<span class="page-info">Page ${state.results.currentPage} of ${state.results.totalPages}</span>`;

        if (state.results.currentPage < state.results.totalPages) {
            html += `<button class="btn-pagination" onclick="loadResultsPage(${state.results.currentPage + 1})">
                Next <i class="fas fa-chevron-right"></i>
            </button>`;
        }

        container.innerHTML = html;
    }

    // ==================== DASHBOARD ====================

    let dashboardStatsCache = null;

    /**
     * Load dashboard statistics
     */
    async function loadDashboardStats() {
        // Return cached data if available
        if (dashboardStatsCache) {
            updateDashboardUI(dashboardStatsCache);
            return dashboardStatsCache;
        }

        try {
            const data = await apiCall('dashboard/overview/');
            
            if (data) {
                dashboardStatsCache = data;
                updateDashboardUI(data);
                return data;
            }
        } catch (error) {
            console.error('Error loading dashboard stats:', error);
            // Show error state
            document.getElementById('dashboard-total-students').textContent = 'Error';
            document.getElementById('dashboard-total-departments').textContent = 'Error';
            document.getElementById('dashboard-total-courses').textContent = 'Error';
            document.getElementById('dashboard-total-lecturers').textContent = 'Error';
        }
    }

    /**
     * Update dashboard UI with statistics
     */
    function updateDashboardUI(data) {
        // Update overview cards
        document.getElementById('dashboard-total-students').textContent = data.total_students || 0;
        document.getElementById('dashboard-students-status').textContent = 'Active';
        document.getElementById('dashboard-students-status').className = 'card-change positive';

        document.getElementById('dashboard-total-departments').textContent = data.total_departments || 0;
        document.getElementById('dashboard-departments-status').textContent = 'Active';
        document.getElementById('dashboard-departments-status').className = 'card-change positive';

        document.getElementById('dashboard-total-courses').textContent = data.total_courses || 0;
        document.getElementById('dashboard-courses-status').textContent = 'Active';
        document.getElementById('dashboard-courses-status').className = 'card-change positive';

        document.getElementById('dashboard-total-lecturers').textContent = data.total_lecturers || 0;
        document.getElementById('dashboard-lecturers-status').textContent = 'Active';
        document.getElementById('dashboard-lecturers-status').className = 'card-change positive';

        // Update recent students table
        const tbody = document.getElementById('dashboard-recent-students');
        if (tbody) {
            if (data.recent_students && data.recent_students.length > 0) {
                tbody.innerHTML = data.recent_students.map(student => `
                    <tr>
                        <td>${student.admission_number || '-'}</td>
                        <td>${student.full_name || '-'}</td>
                        <td>${student.created_at || '-'}</td>
                    </tr>
                `).join('');
            } else {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="3" class="empty-state">
                            <i class="fas fa-user-graduate"></i>
                            <p>No recent students</p>
                        </td>
                    </tr>
                `;
            }
        }
    }

    /**
     * Refresh dashboard stats (clear cache and reload)
     */
    function refreshDashboardStats() {
        dashboardStatsCache = null;
        return loadDashboardStats();
    }

    // ==================== UTILITY FUNCTIONS ====================

    function showLoadingState(type) {
        const tbody = document.getElementById(`${type}-tbody`);
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="loading-row">
                        <i class="fas fa-spinner fa-spin"></i> Loading...
                    </td>
                </tr>
            `;
        }
    }

    function hideLoadingState(type) {
        // Loading state is cleared when table is rendered
    }

    function closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('active');
            const form = modal.querySelector('form');
            if (form) {
                form.reset();
                form.dataset.editId = '';
            }
        }
    }

    function openModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('active');
        }
    }

    // ==================== GLOBAL FUNCTIONS ====================

    // Students
    window.loadStudentsPage = (page) => fetchStudents(page);
    window.viewStudentDetails = async (id, event) => {
        // Prevent row click if clicking on action buttons
        if (event && event.target.closest('.actions, .btn-icon')) {
            return;
        }
        
        const student = state.students.data.find(s => s.id === id);
        if (student) {
            // Set view mode flag
            document.getElementById('student-form').dataset.viewMode = 'true';
            document.getElementById('student-form').dataset.editId = '';
            
            // Load courses first before setting the value
            if (typeof loadStudentCourseOptions === 'function') {
                await loadStudentCourseOptions();
            }
            
            // Set values after courses are loaded
            document.getElementById('student-admission-number').value = student.admission_number || '';
            document.getElementById('student-full-name').value = student.full_name || '';
            document.getElementById('student-email').value = student.email || '';
            document.getElementById('student-phone').value = student.phone || '';
            document.getElementById('student-gender').value = student.gender || 'M';
            document.getElementById('student-year').value = student.year || 1;
            document.getElementById('student-date-of-birth').value = student.date_of_birth || '';
            document.getElementById('student-current-semester').value = student.current_semester || '';
            document.getElementById('student-course').value = student.course_id || '';
            
            // Make all fields read-only
            document.getElementById('student-admission-number').disabled = true;
            document.getElementById('student-full-name').disabled = true;
            document.getElementById('student-email').disabled = true;
            document.getElementById('student-phone').disabled = true;
            document.getElementById('student-gender').disabled = true;
            document.getElementById('student-year').disabled = true;
            document.getElementById('student-date-of-birth').disabled = true;
            document.getElementById('student-current-semester').disabled = true;
            document.getElementById('student-course').disabled = true;
            
            // Update modal title
            document.getElementById('student-modal-title').textContent = 'Student Details';
            
            // Hide submit button, show only close button
            const submitButton = document.querySelector('#student-form button[type="submit"]');
            if (submitButton) {
                submitButton.style.display = 'none';
            }
            
            openModal('student-modal');
        }
    };
    
    window.editStudent = async (id) => {
        const student = state.students.data.find(s => s.id === id);
        if (student) {
            // Remove view mode flag
            document.getElementById('student-form').dataset.viewMode = '';
            document.getElementById('student-form').dataset.editId = id;
            
            // Load courses first before setting the value
            if (typeof loadStudentCourseOptions === 'function') {
                await loadStudentCourseOptions();
            }
            
            // Then set values after courses are loaded
            document.getElementById('student-admission-number').value = student.admission_number || '';
            document.getElementById('student-full-name').value = student.full_name || '';
            document.getElementById('student-email').value = student.email || '';
            document.getElementById('student-phone').value = student.phone || '';
            document.getElementById('student-gender').value = student.gender || 'M';
            document.getElementById('student-year').value = student.year || 1;
            document.getElementById('student-date-of-birth').value = student.date_of_birth || '';
            document.getElementById('student-current-semester').value = student.current_semester || '';
            document.getElementById('student-course').value = student.course_id || '';
            document.getElementById('student-has-ream-paper').checked = student.has_ream_paper || false;
            document.getElementById('student-is-sponsored').checked = student.is_sponsored || false;
            document.getElementById('student-sponsorship-discount-type').value = student.sponsorship_discount_type || '';
            document.getElementById('student-sponsorship-discount-value').value = student.sponsorship_discount_value || '';
            
            // Show/hide sponsorship fields based on checkbox
            const sponsorshipFields = document.getElementById('sponsorship-fields');
            if (student.is_sponsored && sponsorshipFields) {
                sponsorshipFields.style.display = 'block';
            } else if (sponsorshipFields) {
                sponsorshipFields.style.display = 'none';
            }
            
            // Set max semester based on college settings
            if (typeof getSemestersPerYear === 'function') {
                const maxSemesters = await getSemestersPerYear();
                const semesterInput = document.getElementById('student-current-semester');
                if (semesterInput) {
                    semesterInput.setAttribute('max', maxSemesters);
                }
            }
            
            // Set max year based on selected course
            if (student.course_id && typeof studentCoursesData !== 'undefined') {
                const selectedCourse = studentCoursesData.find(c => c.id === parseInt(student.course_id));
                if (selectedCourse) {
                    const maxYear = selectedCourse.duration || selectedCourse.duration_years || 5;
                    document.getElementById('student-year').setAttribute('max', maxYear);
                }
            }
            
            // Enable all fields for editing
            document.getElementById('student-admission-number').disabled = false;
            document.getElementById('student-full-name').disabled = false;
            document.getElementById('student-email').disabled = false;
            document.getElementById('student-phone').disabled = false;
            document.getElementById('student-gender').disabled = false;
            document.getElementById('student-year').disabled = false;
            document.getElementById('student-date-of-birth').disabled = false;
            document.getElementById('student-current-semester').disabled = false;
            document.getElementById('student-course').disabled = false;
            document.getElementById('student-has-ream-paper').disabled = false;
            document.getElementById('student-is-sponsored').disabled = false;
            document.getElementById('student-sponsorship-discount-type').disabled = false;
            document.getElementById('student-sponsorship-discount-value').disabled = false;
            
            // Update modal title
            document.getElementById('student-modal-title').textContent = 'Edit Student';
            
            // Show submit button
            const submitButton = document.querySelector('#student-form button[type="submit"]');
            if (submitButton) {
                submitButton.style.display = '';
            }
            
            openModal('student-modal');
        }
    };
    window.deleteStudent = (id) => deleteStudent(id);
    window.updateStudentStatus = (id, status) => updateStudentStatus(id, status);

    // Courses
    window.loadCoursesPage = (page) => fetchCourses(page);
    window.editCourse = async (id) => {
        const course = state.courses.data.find(c => c.id === id);
        if (course) {
            document.getElementById('course-form').dataset.editId = id;
            document.getElementById('course-code').value = course.code || '';
            document.getElementById('course-name').value = course.name || '';
            document.getElementById('course-duration').value = course.duration || 1;
            document.getElementById('course-admission-requirements').value = course.admission_requirements || '';
            
            // Load departments and set the selected department
            try {
                const deptData = await fetchDepartments(1, '', true);  // Skip section check
                const deptSelect = document.getElementById('course-department');
                if (deptSelect && deptData && deptData.results) {
                    deptSelect.innerHTML = '<option value="">Select Department</option>';
                    deptData.results.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.name;
                        option.textContent = `${dept.code} - ${dept.name}`;
                        // Set selected if this course belongs to this department
                        if (course.department_name && course.department_name === dept.name) {
                            option.selected = true;
                        }
                        deptSelect.appendChild(option);
                    });
                }
            } catch (error) {
                console.error('Error loading departments for edit:', error);
            }
            
            // Set global course if exists
            if (course.global_course_id && window.selectGlobalCourse) {
                window.selectGlobalCourse(
                    course.global_course_id, 
                    course.global_course_name || '', 
                    course.global_course_level || ''
                );
            } else if (window.clearGlobalCourseSelection) {
                window.clearGlobalCourseSelection();
            }
            
            openModal('course-modal');
        }
    };
    window.deleteCourse = (id) => deleteCourse(id);

    // Units - New functions
    window.searchUnitsWithFilters = searchUnitsWithFilters;
    window.showUnitDetail = showUnitDetail;
    window.closeUnitDetailModal = closeUnitDetailModal;
    window.loadUnitsBySemester = loadUnitsBySemester;
    window.renderUnitsList = renderUnitsList;
    window.closeUnitDetail = closeUnitDetail;
    window.editUnitFromDetail = editUnitFromDetail;
    window.deleteUnitFromDetail = deleteUnitFromDetail;
    window.loadLecturerUnits = loadLecturerUnits;
    window.initializeUnitsSection = initializeUnitsSection;
    
    // Keep old editUnit for modal compatibility
    window.editUnit = async (id) => {
        // Try to get unit from current search results or load it
        let unit = null;
        if (state.units && state.units.data) {
            unit = state.units.data.find(u => u.id === id);
        }
        
        // If not found, fetch unit detail
        if (!unit) {
            try {
                const data = await apiCall(`units/${id}/`);
                if (data) unit = data;
            } catch (error) {
                console.error('Error loading unit:', error);
            }
        }
        
        if (unit) {
            document.getElementById('unit-form').dataset.editId = id;
            document.getElementById('unit-code').value = unit.code || '';
            document.getElementById('unit-name').value = unit.name || '';
            document.getElementById('unit-semester').value = unit.semester || 1;
            
            // Set global unit if exists
            if (unit.global_unit_id && window.selectGlobalUnit) {
                window.selectGlobalUnit(
                    unit.global_unit_id, 
                    unit.global_unit_code || '', 
                    unit.global_unit_name || ''
                );
            } else if (window.clearGlobalUnitSelection) {
                window.clearGlobalUnitSelection();
            }
            
            // Load lecturers if not already loaded
            if (window.loadLecturersForUnit) {
                await window.loadLecturersForUnit();
            }
            
            // Set lecturer
            if (unit.lecturer_id) {
                document.getElementById('unit-lecturer').value = unit.lecturer_id;
            } else {
                document.getElementById('unit-lecturer').value = '';
            }
            
            openModal('unit-modal');
        }
    };
    
    // Keep deleteUnit for compatibility
    window.deleteUnit = async (id) => {
        await deleteUnitFromDetail(id);
    };

    // Departments
    window.loadDepartmentsPage = (page) => fetchDepartments(page);
    window.editDepartment = async (id) => {
        const dept = state.departments.data.find(d => d.id === id);
        if (dept) {
            const form = document.getElementById('department-form');
            form.dataset.editId = id;
            form.dataset.oldName = dept.name || '';  // Store original name for identification
            document.getElementById('department-code').value = dept.code || '';
            document.getElementById('department-name').value = dept.name || '';
            document.getElementById('department-description').value = dept.description || '';
            openModal('department-modal');
        }
    };
    window.deleteDepartment = (id) => deleteDepartment(id);

    // Lecturers
    window.loadLecturersPage = (page) => fetchLecturers(page);
    window.editLecturer = async (id) => {
        const lecturer = state.lecturers.data.find(l => l.id === id);
        if (lecturer) {
            document.getElementById('lecturer-form').dataset.editId = id;
            document.getElementById('lecturer-username').value = lecturer.username || '';
            document.getElementById('lecturer-first-name').value = lecturer.first_name || '';
            document.getElementById('lecturer-last-name').value = lecturer.last_name || '';
            document.getElementById('lecturer-email').value = lecturer.email || '';
            document.getElementById('lecturer-phone').value = lecturer.phone || '';
            
            // Handle role field (only for college admins)
            const isAdmin = window.IS_COLLEGE_ADMIN || false;
            const roleGroup = document.getElementById('lecturer-role-group');
            const roleSelect = document.getElementById('lecturer-role');
            const roleBadge = document.getElementById('lecturer-role-badge');
            const currentUserId = window.CURRENT_USER_ID || null;
            const isEditingSelf = currentUserId && parseInt(currentUserId) === parseInt(id);
            
            if (isAdmin && roleGroup && roleSelect && roleBadge) {
                // Show role field
                roleGroup.style.display = 'block';
                
                // Set current role
                const currentRole = lecturer.role || 'lecturer';
                roleSelect.value = currentRole;
                
                // Store original role for comparison
                roleSelect.dataset.originalRole = currentRole;
                document.getElementById('lecturer-form').dataset.originalRole = currentRole;
                
                // Update badge
                updateLecturerRoleBadge(currentRole);
                
                // Disable if editing own account
                if (isEditingSelf) {
                    roleSelect.disabled = true;
                    roleSelect.title = 'You cannot change your own role';
                } else {
                    roleSelect.disabled = false;
                    roleSelect.title = '';
                }
                
                // Set up role change detection (remove existing listener first to avoid duplicates)
                const newRoleSelect = roleSelect.cloneNode(true);
                roleSelect.parentNode.replaceChild(newRoleSelect, roleSelect);
                newRoleSelect.addEventListener('change', handleLecturerRoleChange);
            } else if (roleGroup) {
                // Hide role field for non-admins
                roleGroup.style.display = 'none';
            }
            
            // Hide confirmation initially
            const confirmationDiv = document.getElementById('lecturer-role-confirmation');
            if (confirmationDiv) {
                confirmationDiv.style.display = 'none';
            }
            
            openModal('lecturer-modal');
        }
    };
    
    function updateLecturerRoleBadge(role) {
        const badge = document.getElementById('lecturer-role-badge');
        if (!badge) return;
        
        if (role === 'college_admin') {
            badge.textContent = 'College Admin';
            badge.className = 'badge badge-success';
        } else {
            badge.textContent = 'Lecturer';
            badge.className = 'badge badge-info';
        }
    }
    
    function handleLecturerRoleChange() {
        const roleSelect = document.getElementById('lecturer-role');
        const confirmationDiv = document.getElementById('lecturer-role-confirmation');
        const confirmCheckbox = document.getElementById('lecturer-role-confirm-checkbox');
        const form = document.getElementById('lecturer-form');
        const originalRole = roleSelect ? (roleSelect.dataset.originalRole || form.dataset.originalRole) : '';
        const newRole = roleSelect ? roleSelect.value : '';
        const submitBtn = document.getElementById('lecturer-submit-btn');
        const btnText = submitBtn ? submitBtn.querySelector('.btn-text') : null;
        
        if (!roleSelect || !confirmationDiv) return;
        
        // Update badge
        updateLecturerRoleBadge(newRole);
        
        // Update submit button text
        if (btnText) {
            if (newRole !== originalRole) {
                btnText.textContent = 'Save Changes & Update Role';
            } else {
                btnText.textContent = 'Save Changes';
            }
        }
        
        // Show/hide confirmation based on role change
        if (newRole !== originalRole) {
            confirmationDiv.style.display = 'block';
            roleSelect.style.borderColor = 'var(--warning-color)';
            if (confirmCheckbox) confirmCheckbox.checked = false;
        } else {
            confirmationDiv.style.display = 'none';
            roleSelect.style.borderColor = '';
        }
    }
    
    // Make functions globally accessible
    window.updateLecturerRoleBadge = updateLecturerRoleBadge;
    window.handleLecturerRoleChange = handleLecturerRoleChange;
    window.deleteLecturer = (id) => deleteLecturer(id);
    window.updateLecturerStatus = (id, action) => updateLecturerStatus(id, action);

    // Enrollments
    window.loadEnrollmentsPage = (page) => fetchEnrollments(page);
    window.editEnrollment = async (id) => {
        const enrollment = state.enrollments.data.find(e => e.id === id);
        if (enrollment) {
            // Update modal title
            const modalTitle = document.getElementById('enrollment-modal-title');
            const submitText = document.getElementById('enrollment-submit-text');
            if (modalTitle) modalTitle.textContent = 'Edit Enrollment';
            if (submitText) submitText.textContent = 'Update Enrollment';
            
            document.getElementById('enrollment-form').dataset.editId = id;
            
            // Load students and units if functions exist
            if (typeof window.loadEnrollmentFormStudents === 'function') {
                await window.loadEnrollmentFormStudents();
            }
            if (typeof window.loadEnrollmentFormUnits === 'function') {
                await window.loadEnrollmentFormUnits();
            }
            
            // Set values after dropdowns are loaded
            const studentSelect = document.getElementById('enrollment-student');
            const unitSelect = document.getElementById('enrollment-unit');
            const yearSelect = document.getElementById('enrollment-academic-year');
            const semesterSelect = document.getElementById('enrollment-semester');
            
            // Set student value - ensure the option exists in the dropdown
            if (studentSelect && enrollment.student_id) {
                // Check if the student option exists, if not, add it
                const studentOption = studentSelect.querySelector(`option[value="${enrollment.student_id}"]`);
                if (!studentOption && enrollment.student_name && enrollment.student_admission) {
                    // Add the student option if it doesn't exist
                    const option = document.createElement('option');
                    option.value = enrollment.student_id;
                    option.textContent = `${enrollment.student_name} (${enrollment.student_admission})`;
                    studentSelect.appendChild(option);
                }
                studentSelect.value = enrollment.student_id;
            }
            
            // Set unit value - ensure the option exists in the dropdown
            if (unitSelect && enrollment.unit_id) {
                // Check if the unit option exists, if not, add it
                const unitOption = unitSelect.querySelector(`option[value="${enrollment.unit_id}"]`);
                if (!unitOption && enrollment.unit_code && enrollment.unit_name) {
                    // Add the unit option if it doesn't exist
                    const option = document.createElement('option');
                    option.value = enrollment.unit_id;
                    option.textContent = `${enrollment.unit_code} - ${enrollment.unit_name}`;
                    unitSelect.appendChild(option);
                }
                unitSelect.value = enrollment.unit_id;
            }
            
            // Set academic year and semester
            if (yearSelect) {
                yearSelect.value = enrollment.academic_year || '';
            }
            if (semesterSelect) {
                semesterSelect.value = enrollment.semester || 1;
            }
            
            openModal('enrollment-modal');
        }
    };
    window.deleteEnrollment = (id) => deleteEnrollment(id);

    // Results
    window.loadResultsPage = (page) => fetchResults(page);
    // Function to update result input fields with max values from grading criteria
    async function updateResultInputFields() {
        try {
            let criteria = null;
            if (window.COLLEGE_SLUG) {
                try {
                    const response = await fetch(`/api/${window.COLLEGE_SLUG}/admin/grading-system/`, {
                        headers: { 'X-CSRFToken': window.csrftoken || '' }
                    });
                    // Handle 403 silently (unauthorized access for lecturers)
                    if (response.ok) {
                        const data = await response.json();
                        if (!data.error && data.grading_criteria) {
                            criteria = data.grading_criteria;
                        }
                    }
                    // Silently ignore 403 errors - lecturers don't have admin access
                } catch (fetchError) {
                    // Silently handle network errors or 403s
                    if (fetchError.name !== 'TypeError') {
                        // Only log non-network errors
                        console.error('Error fetching grading criteria:', fetchError);
                    }
                }
            }
            
            // Use configured max marks or defaults (cat_weight and exam_weight represent max marks)
            const maxCat = criteria ? criteria.cat_weight : 30;
            const maxExam = criteria ? criteria.exam_weight : 70;
            
            // Update input fields
            const catInput = document.getElementById('result-cat-marks');
            const examInput = document.getElementById('result-exam-marks');
            const catLabel = document.getElementById('result-cat-label');
            const examLabel = document.getElementById('result-exam-label');
            
            if (catInput) {
                catInput.max = maxCat;
            }
            if (catLabel) {
                catLabel.textContent = `CAT Marks (out of ${maxCat})`;
            }
            
            if (examInput) {
                examInput.max = maxExam;
            }
            if (examLabel) {
                examLabel.textContent = `Exam Marks (out of ${maxExam})`;
            }
        } catch (error) {
            console.error('Error updating result input fields:', error);
        }
    }

    window.editResult = async (enrollmentId) => {
        const result = state.results.data.find(r => r.enrollment_id === enrollmentId);
        if (result) {
            // Update input fields with max values from settings
            await updateResultInputFields();
            
            document.getElementById('result-form').dataset.enrollmentId = enrollmentId;
            document.getElementById('result-form').dataset.resultId = result.id || '';
            document.getElementById('result-cat-marks').value = result.cat_marks !== null ? result.cat_marks : '';
            document.getElementById('result-exam-marks').value = result.exam_marks !== null ? result.exam_marks : '';
            
            // Recalculate total after setting values
            if (typeof window.calculateTotal === 'function') {
                window.calculateTotal();
            }
            
            // Show/hide submit button based on status and user role
            const submitBtn = document.getElementById('result-submit-btn');
            if (submitBtn) {
                const isLecturer = window.USER_ROLE === 'lecturer';
                const isDraft = result.status === 'draft' || !result.status;
                submitBtn.style.display = (isLecturer && isDraft && result.can_edit) ? 'inline-block' : 'none';
            }
            
            // Disable fields if submitted and user is lecturer
            const isLecturer = window.USER_ROLE === 'lecturer';
            const isSubmitted = result.status === 'submitted';
            const catInput = document.getElementById('result-cat-marks');
            const examInput = document.getElementById('result-exam-marks');
            if (catInput && examInput) {
                if (isLecturer && isSubmitted) {
                    catInput.disabled = true;
                    examInput.disabled = true;
                } else {
                    catInput.disabled = false;
                    examInput.disabled = false;
                }
            }
            
            openModal('result-modal');
        }
    };
    
    window.submitResult = async function() {
        const form = document.getElementById('result-form');
        const resultId = form.dataset.resultId;
        
        if (!resultId) {
            showToast('error', 'Result ID not found');
            return;
        }
        
        try {
            const data = await apiCall(`results/${resultId}/submit/`, {
                method: 'POST'
            });
            
            if (data && data.success) {
                showToast('success', data.message || 'Result submitted successfully');
                closeModal('result-modal');
                await fetchResults(state.results.currentPage);
            }
        } catch (error) {
            console.error('Error submitting result:', error);
            const errorMsg = error.message || 'Failed to submit result';
            showToast('error', errorMsg);
        }
    };

    // Initialize data loading when sections are shown
    document.addEventListener('DOMContentLoaded', function() {
        // Listen for section changes
        const navLinks = document.querySelectorAll('.nav-link[data-section]');
        navLinks.forEach(link => {
            link.addEventListener('click', function() {
                const sectionId = this.getAttribute('data-section');
                
                // Load data when section is shown
                setTimeout(() => {
                    if (sectionId === 'dashboard-section') {
                        loadDashboardStats();
                    } else if (sectionId === 'students-section') {
                        fetchStudents();
                    } else if (sectionId === 'courses-section') {
                        fetchCourses();
                    } else if (sectionId === 'units-section') {
                        initializeUnitsSection();
                    } else if (sectionId === 'departments-section') {
                        fetchDepartments();
                    } else if (sectionId === 'lecturers-section') {
                        fetchLecturers();
                    } else if (sectionId === 'courseunits-section') {
                        // Initialize course unit management when section is shown
                        if (typeof initializeCourseUnitManagement === 'function') {
                            initializeCourseUnitManagement();
                        }
                    } else if (sectionId === 'exams-section') {
                        // Exams section loads enrollments by default
                        const enrollmentsTab = document.getElementById('enrollments-tab');
                        if (enrollmentsTab) enrollmentsTab.click();
                    } else if (sectionId === 'timetable-section') {
                        loadTimetableCourseOptions();
                        loadTimetableYearOptions();
                        // Populate semester dropdowns
                        if (typeof populateSemesterDropdown === 'function') {
                            populateSemesterDropdown('general-timetable-semester-filter', true);
                            populateSemesterDropdown('course-timetable-semester-filter', true);
                        }
                        // Initialize with general tab
                        setTimeout(() => {
                            switchTimetableTab('general');
                        }, 200);
                    }
                }, 100);
            });
        });

        // Load data on initial load based on active section
        const dashboardSection = document.getElementById('dashboard-section');
        const courseunitsSection = document.getElementById('courseunits-section');
        const unitsSection = document.getElementById('units-section');
        
        if (dashboardSection && dashboardSection.classList.contains('active')) {
            loadDashboardStats();
        } else if (courseunitsSection && courseunitsSection.classList.contains('active')) {
            // Initialize course unit management if it's the active section on page load
            if (typeof initializeCourseUnitManagement === 'function') {
                initializeCourseUnitManagement();
            }
        } else if (unitsSection && unitsSection.classList.contains('active')) {
            // Initialize units section if it's the active section on page load
            if (typeof initializeUnitsSection === 'function') {
                initializeUnitsSection();
            }
        }
    });

    // ============================================
    // Timetable Management Functions
    // ============================================
    
    let timetablesCurrentPage = 1;
    let timetablesTotalPages = 1;
    let currentTimetableTab = 'general';
    let generalTimetablesCurrentPage = 1;
    let courseTimetablesCurrentPage = 1;
    
    function switchTimetableTab(tab) {
        currentTimetableTab = tab;
        
        // Update tab buttons
        document.querySelectorAll('.timetable-tabs .tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.timetable-tab-content').forEach(content => content.classList.remove('active'));
        
        if (tab === 'general') {
            document.getElementById('general-timetable-tab')?.classList.add('active');
            document.getElementById('general-timetable-tab-content')?.classList.add('active');
            loadTimetables(1, 'general');
        } else {
            document.getElementById('course-timetable-tab')?.classList.add('active');
            document.getElementById('course-timetable-tab-content')?.classList.add('active');
            loadTimetables(1, 'course');
        }
    }
    
    function loadTimetables(page = 1, tab = null) {
        if (!window.COLLEGE_SLUG) return;
        
        const activeTab = tab || currentTimetableTab;
        const isGeneral = activeTab === 'general';
        
        const containerId = isGeneral ? 'general-timetables-container' : 'course-timetables-container';
        const tbodyId = isGeneral ? 'general-timetables-tbody' : 'course-timetables-tbody';
        const loadingId = isGeneral ? 'general-timetables-loading' : 'course-timetables-loading';
        const emptyId = isGeneral ? 'general-timetables-empty' : 'course-timetables-empty';
        
        const container = document.getElementById(containerId);
        const tbody = document.getElementById(tbodyId);
        const loading = document.getElementById(loadingId);
        const empty = document.getElementById(emptyId);
        
        if (!container || !tbody) return;
        
        // Show loading, hide content and empty
        if (loading) loading.style.display = 'block';
        if (tbody) tbody.style.display = 'none';
        if (empty) empty.style.display = 'none';
        
        // Get filters based on active tab
        let url = `/api/${window.COLLEGE_SLUG}/timetables/?page=${page}`;
        
        if (isGeneral) {
            // General timetable filters
            url += `&timetable_type=general`;
            const yearFilter = document.getElementById('general-timetable-year-filter')?.value || '';
            const semesterFilter = document.getElementById('general-timetable-semester-filter')?.value || '';
            if (yearFilter) url += `&academic_year=${yearFilter}`;
            if (semesterFilter) url += `&semester=${semesterFilter}`;
        } else {
            // Course-specific timetable filters
            url += `&timetable_type=course_specific`;
            const courseFilter = document.getElementById('course-timetable-course-filter')?.value || '';
            const yearFilter = document.getElementById('course-timetable-year-filter')?.value || '';
            const semesterFilter = document.getElementById('course-timetable-semester-filter')?.value || '';
            if (courseFilter) url += `&course_id=${courseFilter}`;
            if (yearFilter) url += `&academic_year=${yearFilter}`;
            if (semesterFilter) url += `&semester=${semesterFilter}`;
        }
        
        fetch(url, {
            method: 'GET',
            headers: {
                'X-CSRFToken': window.csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (isGeneral) {
                generalTimetablesCurrentPage = data.page || 1;
            } else {
                courseTimetablesCurrentPage = data.page || 1;
            }
            renderTimetablesTable(data.results || [], isGeneral);
            renderTimetablesPagination(data, isGeneral);
            
            // Hide loading, show content or empty
            if (loading) loading.style.display = 'none';
            if (data.results && data.results.length > 0) {
                if (tbody) tbody.style.display = 'grid';
                if (empty) empty.style.display = 'none';
            } else {
                if (tbody) tbody.style.display = 'none';
                if (empty) empty.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error loading timetables:', error);
            if (loading) loading.style.display = 'none';
            if (tbody) {
                tbody.style.display = 'none';
                tbody.innerHTML = '';
            }
            if (empty) {
                empty.style.display = 'block';
                empty.innerHTML = '<i class="fas fa-exclamation-circle"></i><p>Error loading timetables</p>';
            }
        });
    }
    
    function renderTimetablesTable(timetables, isGeneral) {
        const tbodyId = isGeneral ? 'general-timetables-tbody' : 'course-timetables-tbody';
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        
        if (timetables.length === 0) {
            tbody.innerHTML = '';
            return;
        }
        
        if (isGeneral) {
            // General timetable forms
            tbody.innerHTML = timetables.map(tt => {
                return `
                    <div class="timetable-form-card">
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Academic Year</label>
                            <div class="timetable-form-value">${tt.academic_year || '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Semester</label>
                            <div class="timetable-form-value">${tt.semester ? `Semester ${tt.semester}` : '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Description</label>
                            <div class="timetable-form-value">${tt.description || '<span class="empty">No description</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Uploaded By</label>
                            <div class="timetable-form-value">${tt.uploaded_by || '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Uploaded At</label>
                            <div class="timetable-form-value">${tt.uploaded_at ? new Date(tt.uploaded_at).toLocaleDateString() : '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-actions">
                            <button class="btn-icon btn-view" onclick="viewTimetable(${tt.id}, '${tt.image_url}')" title="View">
                                <i class="fas fa-eye"></i>
                            </button>
                            ${window.IS_COLLEGE_ADMIN ? `
                                <button class="btn-icon btn-edit" onclick="editTimetable(${tt.id})" title="Edit">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn-icon btn-danger" onclick="deleteTimetable(${tt.id})" title="Delete">
                                    <i class="fas fa-trash"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            // Course-specific timetable forms
            tbody.innerHTML = timetables.map(tt => {
                return `
                    <div class="timetable-form-card">
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Course</label>
                            <div class="timetable-form-value"><span class="timetable-badge">${tt.course_name || 'Course'}</span></div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Academic Year</label>
                            <div class="timetable-form-value">${tt.academic_year || '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Semester</label>
                            <div class="timetable-form-value">${tt.semester ? `Semester ${tt.semester}` : '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Description</label>
                            <div class="timetable-form-value">${tt.description || '<span class="empty">No description</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Uploaded By</label>
                            <div class="timetable-form-value">${tt.uploaded_by || '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-field">
                            <label class="timetable-form-label">Uploaded At</label>
                            <div class="timetable-form-value">${tt.uploaded_at ? new Date(tt.uploaded_at).toLocaleDateString() : '<span class="empty">-</span>'}</div>
                        </div>
                        <div class="timetable-form-actions">
                            <button class="btn-icon btn-view" onclick="viewTimetable(${tt.id}, '${tt.image_url}')" title="View">
                                <i class="fas fa-eye"></i>
                            </button>
                            ${window.IS_COLLEGE_ADMIN ? `
                                <button class="btn-icon btn-edit" onclick="editTimetable(${tt.id})" title="Edit">
                                    <i class="fas fa-edit"></i>
                                </button>
                                <button class="btn-icon btn-danger" onclick="deleteTimetable(${tt.id})" title="Delete">
                                    <i class="fas fa-trash"></i>
                                </button>
                            ` : ''}
                        </div>
                    </div>
                `;
            }).join('');
        }
    }
    
    function renderTimetablesPagination(data, isGeneral) {
        const paginationId = isGeneral ? 'general-timetables-pagination' : 'course-timetables-pagination';
        const pagination = document.getElementById(paginationId);
        if (!pagination) return;
        
        if (data.total_pages <= 1) {
            pagination.innerHTML = '';
            return;
        }
        
        const currentPage = isGeneral ? generalTimetablesCurrentPage : courseTimetablesCurrentPage;
        let html = '<div class="pagination-controls">';
        if (data.previous) {
            html += `<button class="btn btn-sm" onclick="loadTimetables(${data.previous}, '${isGeneral ? 'general' : 'course'}')">Previous</button>`;
        }
        html += `<span>Page ${data.page} of ${data.total_pages}</span>`;
        if (data.next) {
            html += `<button class="btn btn-sm" onclick="loadTimetables(${data.next}, '${isGeneral ? 'general' : 'course'}')">Next</button>`;
        }
        html += '</div>';
        pagination.innerHTML = html;
    }
    
    function loadTimetableCourseOptions() {
        if (!window.COLLEGE_SLUG) return;
        
        const select = document.getElementById('timetable-course');
        const courseFilterSelect = document.getElementById('course-timetable-course-filter');
        
        fetch(`/api/${window.COLLEGE_SLUG}/courses/`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': window.csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            const courses = data.results || [];
            
            // Populate upload modal select
            if (select) {
                select.innerHTML = '<option value="">Select Course</option>' + 
                    courses.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
            }
            
            // Populate course-specific filter select
            if (courseFilterSelect) {
                courseFilterSelect.innerHTML = '<option value="">All Courses</option>' + 
                    courses.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
            }
        })
        .catch(error => {
            console.error('Error loading courses:', error);
        });
    }
    
    function loadTimetableYearOptions() {
        if (!window.COLLEGE_SLUG) return;
        
        // Load academic years from timetables
        fetch(`/api/${window.COLLEGE_SLUG}/timetables/?page_size=1000`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': window.csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            const timetables = data.results || [];
            const years = [...new Set(timetables.map(tt => tt.academic_year).filter(Boolean))].sort().reverse();
            const semesters = [...new Set(timetables.map(tt => tt.semester).filter(Boolean))].sort((a, b) => a - b);
            
            // Populate general timetable year filter
            const generalYearFilter = document.getElementById('general-timetable-year-filter');
            if (generalYearFilter) {
                generalYearFilter.innerHTML = '<option value="">All Years</option>' + 
                    years.map(year => `<option value="${year}">${year}</option>`).join('');
            }
            
            // Populate course timetable year filter
            const courseYearFilter = document.getElementById('course-timetable-year-filter');
            if (courseYearFilter) {
                courseYearFilter.innerHTML = '<option value="">All Years</option>' + 
                    years.map(year => `<option value="${year}">${year}</option>`).join('');
            }
            
            // Populate semester filters if not already populated
            const generalSemesterFilter = document.getElementById('general-timetable-semester-filter');
            if (generalSemesterFilter && generalSemesterFilter.options.length <= 1) {
                generalSemesterFilter.innerHTML = '<option value="">All Semesters</option>' + 
                    semesters.map(sem => `<option value="${sem}">Semester ${sem}</option>`).join('');
            }
            
            const courseSemesterFilter = document.getElementById('course-timetable-semester-filter');
            if (courseSemesterFilter && courseSemesterFilter.options.length <= 1) {
                courseSemesterFilter.innerHTML = '<option value="">All Semesters</option>' + 
                    semesters.map(sem => `<option value="${sem}">Semester ${sem}</option>`).join('');
            }
        })
        .catch(error => {
            console.error('Error loading years:', error);
        });
    }
    
    function openTimetableModal(timetableId = null) {
        const modal = document.getElementById('timetable-modal');
        const title = document.getElementById('timetable-modal-title');
        const form = document.getElementById('timetable-form');
        const submitBtn = document.getElementById('timetable-submit-btn');
        
        if (!modal) return;
        
        // Reset form
        form.reset();
        document.getElementById('timetable-image-preview').style.display = 'none';
        document.getElementById('timetable-course-group').style.display = 'none';
        document.querySelector('input[name="timetable-type"][value="general"]').checked = true;
        
        if (timetableId) {
            title.textContent = 'Edit Timetable';
            submitBtn.querySelector('.btn-text').textContent = 'Update Timetable';
            loadTimetableForEdit(timetableId);
        } else {
            title.textContent = 'Upload Timetable';
            submitBtn.querySelector('.btn-text').textContent = 'Upload Timetable';
        }
        
        modal.classList.add('active');
    }
    
    function loadTimetableForEdit(timetableId) {
        if (!window.COLLEGE_SLUG) return;
        
        fetch(`/api/${window.COLLEGE_SLUG}/timetables/${timetableId}/`, {
            method: 'GET',
            headers: {
                'X-CSRFToken': window.csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showToast('error', data.error);
                return;
            }
            
            // Set form values
            if (data.course_id) {
                document.querySelector('input[name="timetable-type"][value="course_specific"]').checked = true;
                toggleTimetableCourseField();
                document.getElementById('timetable-course').value = data.course_id;
            }
            
            document.getElementById('timetable-academic-year').value = data.academic_year || '';
            document.getElementById('timetable-semester').value = data.semester || '';
            document.getElementById('timetable-description').value = data.description || '';
            
            // Show preview if image exists
            if (data.image_url) {
                const preview = document.getElementById('timetable-image-preview');
                const img = document.getElementById('timetable-preview-img');
                img.src = data.image_url;
                preview.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error loading timetable:', error);
            showToast('error', 'Error loading timetable details');
        });
    }
    
    function toggleTimetableCourseField() {
        const courseGroup = document.getElementById('timetable-course-group');
        const courseSelect = document.getElementById('timetable-course');
        const type = document.querySelector('input[name="timetable-type"]:checked')?.value;
        
        if (type === 'course_specific') {
            courseGroup.style.display = 'block';
            courseSelect.required = true;
        } else {
            courseGroup.style.display = 'none';
            courseSelect.required = false;
            courseSelect.value = '';
        }
    }
    
    function previewTimetableImage(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        // Validate file type
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
        if (!allowedTypes.includes(file.type)) {
            showToast('error', 'Invalid file type. Please upload JPG, PNG, GIF, or WebP image');
            event.target.value = '';
            return;
        }
        
        // Validate file size (10MB)
        if (file.size > 10 * 1024 * 1024) {
            showToast('error', 'File size exceeds 10MB limit');
            event.target.value = '';
            return;
        }
        
        // Show preview
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('timetable-image-preview');
            const img = document.getElementById('timetable-preview-img');
            img.src = e.target.result;
            preview.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }
    
    function handleTimetableSubmit(event) {
        event.preventDefault();
        
        if (!window.COLLEGE_SLUG) return;
        
        const form = document.getElementById('timetable-form');
        const submitBtn = document.getElementById('timetable-submit-btn');
        const btnText = submitBtn.querySelector('.btn-text');
        const btnLoader = submitBtn.querySelector('.btn-loader');
        
        const type = document.querySelector('input[name="timetable-type"]:checked')?.value;
        const courseId = document.getElementById('timetable-course').value;
        const imageFile = document.getElementById('timetable-image').files[0];
        const academicYear = document.getElementById('timetable-academic-year').value;
        const semester = document.getElementById('timetable-semester').value;
        const description = document.getElementById('timetable-description').value;
        
        // Validation
        if (type === 'course_specific' && !courseId) {
            showToast('error', 'Please select a course for course-specific timetable');
            return;
        }
        
        if (!imageFile && !document.getElementById('timetable-modal-title').textContent.includes('Edit')) {
            showToast('error', 'Please select an image file');
            return;
        }
        
        // Create FormData
        const formData = new FormData();
        if (imageFile) formData.append('image', imageFile);
        if (type === 'course_specific' && courseId) formData.append('course_id', courseId);
        if (academicYear) formData.append('academic_year', academicYear);
        if (semester) formData.append('semester', semester);
        if (description) formData.append('description', description);
        
        // Determine if update or create
        const isEdit = document.getElementById('timetable-modal-title').textContent.includes('Edit');
        const timetableId = form.dataset.timetableId;
        
        const url = isEdit && timetableId 
            ? `/api/${window.COLLEGE_SLUG}/timetables/${timetableId}/`
            : `/api/${window.COLLEGE_SLUG}/timetables/`;
        const method = isEdit ? 'PUT' : 'POST';
        
        // Show loading
        submitBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.style.display = 'inline-block';
        
        fetch(url, {
            method: method,
            headers: {
                'X-CSRFToken': window.csrftoken
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showToast('error', data.error);
                return;
            }
            
            showToast('success', data.message || 'Timetable saved successfully');
            closeModal('timetable-modal');
            loadTimetables(1, currentTimetableTab);
        })
        .catch(error => {
            console.error('Error saving timetable:', error);
            showToast('error', 'Error saving timetable');
        })
        .finally(() => {
            submitBtn.disabled = false;
            btnText.style.display = 'inline-block';
            btnLoader.style.display = 'none';
        });
    }
    
    function editTimetable(timetableId) {
        openTimetableModal(timetableId);
        document.getElementById('timetable-form').dataset.timetableId = timetableId;
    }
    
    function viewTimetable(timetableId, imageUrl) {
        const modal = document.getElementById('timetable-view-modal');
        const img = document.getElementById('timetable-view-img');
        
        if (!modal || !img) return;
        
        img.src = imageUrl;
        modal.style.display = 'flex';
    }
    
    function deleteTimetable(timetableId) {
        if (!confirm('Are you sure you want to delete this timetable?')) return;
        if (!window.COLLEGE_SLUG) return;
        
        fetch(`/api/${window.COLLEGE_SLUG}/timetables/${timetableId}/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': window.csrftoken
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showToast('error', data.error);
                return;
            }
            
            showToast('success', 'Timetable deleted successfully');
            loadTimetables(1, currentTimetableTab);
        })
        .catch(error => {
            console.error('Error deleting timetable:', error);
            showToast('error', 'Error deleting timetable');
        });
    }
    
    function filterTimetables() {
        loadTimetables(1, currentTimetableTab);
    }
    
    function searchTimetables() {
        // Simple search - reload with filters
        loadTimetables(1, currentTimetableTab);
    }
    
    // Export timetable functions
    window.openTimetableModal = openTimetableModal;
    window.toggleTimetableCourseField = toggleTimetableCourseField;
    window.previewTimetableImage = previewTimetableImage;
    window.handleTimetableSubmit = handleTimetableSubmit;
    window.editTimetable = editTimetable;
    window.viewTimetable = viewTimetable;
    window.deleteTimetable = deleteTimetable;
    window.filterTimetables = filterTimetables;
    window.searchTimetables = searchTimetables;
    window.loadTimetables = loadTimetables;
    window.switchTimetableTab = switchTimetableTab;

    // Export functions for use in templates
    window.LandingData = {
        fetchStudents,
        fetchCourses,
        // fetchUnits removed - units now use searchUnitsWithFilters instead
        fetchDepartments,
        fetchLecturers,
        fetchEnrollments,
        fetchResults,
        loadDashboardStats,
        refreshDashboardStats,
        createStudent,
        updateStudent,
        deleteStudent,
        createCourse,
        updateCourse,
        deleteCourse,
        createUnit,
        updateUnit,
        deleteUnit,
        createDepartment,
        updateDepartment,
        deleteDepartment,
        createLecturer,
        updateLecturer,
        deleteLecturer,
        createEnrollment,
        updateEnrollment,
        deleteEnrollment,
        saveResult,
        updateResultInputFields,
        initializeUnitsSection,
        loadUnitsBySemester,
        renderUnitsList,
        showUnitDetail,
        closeUnitDetailModal
    };

})();

