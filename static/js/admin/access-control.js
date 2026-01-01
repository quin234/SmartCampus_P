/**
 * Frontend Access Control
 * Prevents Super Admin from accessing college-specific pages via frontend
 */

(function() {
    'use strict';

    // Check if user is super admin (from Django template or API)
    function isSuperAdmin() {
        // Check if user role is available in window object
        return window.USER_ROLE === 'super_admin' || 
               document.body.dataset.userRole === 'super_admin';
    }

    // Block super admin from accessing college-specific pages
    function enforceAccessControl() {
        if (!isSuperAdmin()) {
            return; // Not a super admin, allow access
        }

        // Get current path
        const path = window.location.pathname;
        
        // List of college-specific paths that super admin should not access
        const collegeSpecificPaths = [
            '/students/',
            '/departments/',
            '/courses/',
            '/units/',
            '/lecturers/',
            '/exams/',
            '/fees/',
            '/announcements/',
            '/timetable/',
            '/settings/'
        ];

        // Check if current path contains any college-specific path
        const isCollegeSpecific = collegeSpecificPaths.some(collegePath => {
            // Match pattern: /{college-slug}/{path}
            const pattern = new RegExp(`/[^/]+${collegePath.replace('/', '\\/')}`);
            return pattern.test(path);
        });

        if (isCollegeSpecific) {
            // Redirect super admin to superadmin dashboard
            console.warn('Super Admin attempted to access college-specific page. Redirecting...');
            window.location.href = '/superadmin/dashboard/';
        }
    }

    // Run on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', enforceAccessControl);
    } else {
        enforceAccessControl();
    }

    // Also run on SPA navigation
    window.addEventListener('spa:page-loaded', enforceAccessControl);

})();

