/**
 * College Registration Page
 * Handles school registration form submission
 */

// API Configuration
const API_BASE_URL = '/api/schools/register';

// Utility Functions
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

function showFieldError(fieldId, message) {
    const errorEl = document.getElementById(`error-${fieldId}`);
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    }
}

function clearFieldError(fieldId) {
    const errorEl = document.getElementById(`error-${fieldId}`);
    if (errorEl) {
        errorEl.textContent = '';
        errorEl.style.display = 'none';
    }
}

function clearAllErrors() {
    document.querySelectorAll('.error-message').forEach(el => {
        el.textContent = '';
        el.style.display = 'none';
    });
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function isValidURL(url) {
    if (!url) return true; // Optional field
    try {
        new URL(url);
        return true;
    } catch {
        return false;
    }
}

// Form Validation
function validateForm(formData) {
    let isValid = true;
    clearAllErrors();

    // School Name
    if (!formData.school_name || !formData.school_name.trim()) {
        showFieldError('school-name', 'School name is required');
        isValid = false;
    }

    // School Type
    if (!formData.school_type) {
        showFieldError('school-type', 'School type is required');
        isValid = false;
    }

    // School Address
    if (!formData.school_address || !formData.school_address.trim()) {
        showFieldError('school-address', 'School address is required');
        isValid = false;
    }

    // County/City
    if (!formData.county_city || !formData.county_city.trim()) {
        showFieldError('county-city', 'County/City is required');
        isValid = false;
    }

    // School Contact
    if (!formData.school_contact_number || !formData.school_contact_number.trim()) {
        showFieldError('school-contact', 'Contact number is required');
        isValid = false;
    }

    // School Email
    if (!formData.school_email || !isValidEmail(formData.school_email)) {
        showFieldError('school-email', 'Valid school email is required');
        isValid = false;
    }

    // School Website (optional but must be valid if provided)
    if (formData.school_website && !isValidURL(formData.school_website)) {
        showFieldError('school-website', 'Please enter a valid URL');
        isValid = false;
    }

    // Owner Full Name
    if (!formData.owner_full_name || !formData.owner_full_name.trim()) {
        showFieldError('owner-name', 'Owner full name is required');
        isValid = false;
    }

    // Position
    if (!formData.position || !formData.position.trim()) {
        showFieldError('position', 'Position is required');
        isValid = false;
    }

    // Owner Email
    if (!formData.owner_email || !isValidEmail(formData.owner_email)) {
        showFieldError('owner-email', 'Valid email is required');
        isValid = false;
    }

    // Owner Phone
    if (!formData.owner_phone || !formData.owner_phone.trim()) {
        showFieldError('owner-phone', 'Phone number is required');
        isValid = false;
    }

    // Username
    if (!formData.username || !formData.username.trim()) {
        showFieldError('username', 'Username is required');
        isValid = false;
    } else if (formData.username.length < 3) {
        showFieldError('username', 'Username must be at least 3 characters');
        isValid = false;
    }

    // Password
    if (!formData.password) {
        showFieldError('password', 'Password is required');
        isValid = false;
    } else if (formData.password.length < 6) {
        showFieldError('password', 'Password must be at least 6 characters');
        isValid = false;
    }

    return isValid;
}

// Form Submission
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('registration-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('.btn-text');
    const btnLoader = submitBtn.querySelector('.btn-loader');
    const passwordToggle = document.getElementById('password-toggle');
    const passwordInput = document.getElementById('password');

    // Password toggle
    if (passwordToggle && passwordInput) {
        passwordToggle.addEventListener('click', () => {
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            const icon = passwordToggle.querySelector('i');
            icon.classList.toggle('fa-eye');
            icon.classList.toggle('fa-eye-slash');
        });
    }

    // Real-time validation
    const inputs = form.querySelectorAll('.form-input');
    inputs.forEach(input => {
        input.addEventListener('blur', () => {
            const fieldName = input.getAttribute('name');
            if (fieldName) {
                const formData = new FormData(form);
                const value = formData.get(fieldName);
                
                // Clear error on blur if field is valid
                if (value && value.trim()) {
                    clearFieldError(input.id);
                }
            }
        });
    });

    // Form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Get form data
        const formData = new FormData(form);
        const data = {};
        formData.forEach((value, key) => {
            data[key] = value;
        });

        // Validate form
        if (!validateForm(data)) {
            showToast('error', 'Please fix the errors in the form');
            return;
        }

        // Show loading state
        submitBtn.disabled = true;
        btnText.style.display = 'none';
        btnLoader.classList.remove('hidden');

        try {
            // API Call: POST /api/schools/register
            const response = await fetch(API_BASE_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok && result.success) {
                showToast('success', 'Registration successful! Redirecting to login...');
                
                // Clear form
                form.reset();
                
                // Redirect to login after 2 seconds
                setTimeout(() => {
                    window.location.href = '/admin/login/';
                }, 2000);
            } else {
                // Handle validation errors from server
                if (result.errors) {
                    Object.keys(result.errors).forEach(field => {
                        const fieldId = field.replace(/_/g, '-');
                        showFieldError(fieldId, result.errors[field][0] || 'Invalid value');
                    });
                }
                showToast('error', result.message || 'Registration failed. Please try again.');
            }
        } catch (error) {
            console.error('Registration error:', error);
            showToast('error', 'An error occurred. Please try again.');
        } finally {
            // Reset button state
            submitBtn.disabled = false;
            btnText.style.display = 'flex';
            btnLoader.classList.add('hidden');
        }
    });
});

