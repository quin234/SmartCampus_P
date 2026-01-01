/**
 * Landing Page Navigation
 * Handles section show/hide functionality for single-page college landing page
 */

(function() {
    'use strict';

    // Initialize navigation when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        initNavigation();
    });

    /**
     * Initialize navigation functionality
     */
    function initNavigation() {
        const navLinks = document.querySelectorAll('.nav-link[data-section]');
        const sections = document.querySelectorAll('.content-section');
        const navItems = document.querySelectorAll('.nav-item[data-section]');

        // Add click handlers to all navigation links
        navLinks.forEach(function(link) {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                
                const targetSectionId = this.getAttribute('data-section');
                
                if (targetSectionId) {
                    // Hide all sections
                    sections.forEach(function(section) {
                        section.classList.remove('active');
                    });

                    // Show target section
                    const targetSection = document.getElementById(targetSectionId);
                    if (targetSection) {
                        targetSection.classList.add('active');
                    }

                    // Update active state in sidebar
                    navItems.forEach(function(item) {
                        item.classList.remove('active');
                    });
                    
                    const activeNavItem = document.querySelector(`.nav-item[data-section="${targetSectionId}"]`);
                    if (activeNavItem) {
                        activeNavItem.classList.add('active');
                    }

                    // Close mobile sidebar if open
                    const sidebar = document.getElementById('sidebar');
                    if (sidebar && sidebar.classList.contains('open')) {
                        sidebar.classList.remove('open');
                    }

                    // Scroll to top of main content
                    const mainContent = document.getElementById('main-content');
                    if (mainContent) {
                        mainContent.scrollTop = 0;
                    }

                    // Load section-specific data
                    if (targetSectionId === 'academic-config-section') {
                        setTimeout(() => {
                            // Load the active tab's content
                            const activeTab = document.querySelector('#academic-config-section .tab-btn.active');
                            if (activeTab) {
                                if (activeTab.id === 'academic-settings-top-tab' && typeof loadAcademicSettings === 'function') {
                                    loadAcademicSettings();
                                } else if (activeTab.id === 'grading-system-top-tab' && typeof loadGradingSystem === 'function') {
                                    loadGradingSystem();
                                } else if (activeTab.id === 'nominal-roll-top-tab' && typeof loadNominalRollSettings === 'function') {
                                    loadNominalRollSettings();
                                } else if (activeTab.id === 'transcript-template-top-tab' && typeof loadTranscriptTemplate === 'function') {
                                    loadTranscriptTemplate();
                                }
                            } else {
                                // Default to academic settings
                                if (typeof loadAcademicSettings === 'function') {
                                    loadAcademicSettings();
                                }
                            }
                        }, 100);
                    } else if (targetSectionId === 'units-section') {
                        // Load semester 1 units by default when units section is opened
                        setTimeout(() => {
                            if (window.LandingData && typeof window.LandingData.initializeUnitsSection === 'function') {
                                window.LandingData.initializeUnitsSection();
                            } else if (typeof initializeUnitsSection === 'function') {
                                initializeUnitsSection();
                            }
                        }, 100);
                    }
                }
            });
        });

        // Set default active section (dashboard)
        const defaultSection = document.getElementById('dashboard-section');
        if (defaultSection) {
            defaultSection.classList.add('active');
        }

        // Ensure dashboard nav item is active by default
        const defaultNavItem = document.querySelector('.nav-item[data-section="dashboard-section"]');
        if (defaultNavItem) {
            defaultNavItem.classList.add('active');
        }
    }

    // Handle browser back/forward buttons
    window.addEventListener('popstate', function(e) {
        // If needed, can restore section state from history
        // For now, just ensure dashboard is shown
        const sections = document.querySelectorAll('.content-section');
        sections.forEach(function(section) {
            section.classList.remove('active');
        });
        
        const dashboardSection = document.getElementById('dashboard-section');
        if (dashboardSection) {
            dashboardSection.classList.add('active');
        }

        // Update nav active state
        const navItems = document.querySelectorAll('.nav-item[data-section]');
        navItems.forEach(function(item) {
            item.classList.remove('active');
        });
        
        const defaultNavItem = document.querySelector('.nav-item[data-section="dashboard-section"]');
        if (defaultNavItem) {
            defaultNavItem.classList.add('active');
        }
    });

})();

