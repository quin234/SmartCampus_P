// Form validation and submission
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('register-form');
    const formMessages = document.getElementById('form-messages');
    
    // Password toggle functionality
    const passwordToggle = document.getElementById('password-toggle');
    const passwordInput = document.getElementById('password');
    
    if (passwordToggle && passwordInput) {
        passwordToggle.addEventListener('click', function() {
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);
            const icon = passwordToggle.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-eye');
                icon.classList.toggle('fa-eye-slash');
            }
        });
    }
    
    // Clear error messages on input
    const inputs = form.querySelectorAll('input, select, textarea');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            clearFieldError(this);
        });
    });

    // Form submission
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        // Clear previous messages
        clearMessages();
        
        // Validate form
        if (!validateForm()) {
            return;
        }
        
        // Disable submit button
        const submitButton = form.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.textContent = 'Submitting...';
        
        try {
            // Prepare form data
            const formData = new FormData(form);
            
            // Convert FormData to JSON (excluding file)
            const data = {};
            const logoFile = formData.get('school_logo');
            
            for (let [key, value] of formData.entries()) {
                if (key !== 'school_logo') {
                    data[key] = value;
                }
            }
            
            // If logo is selected, we'll send it separately or include in FormData
            // For now, we'll send JSON and handle logo separately if needed
            const response = await fetch('/api/schools/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            
            if (response.ok && result.success) {
                showSuccess('Registration successful! Your account has been created. Redirecting to login...');
                form.reset();
                // Redirect to login after 2 seconds
                setTimeout(() => {
                    window.location.href = '/admin/login/';
                }, 2000);
            } else {
                // Handle validation errors from server
                if (result.errors) {
                    displayServerErrors(result.errors);
                } else {
                    showError(result.message || 'An error occurred. Please try again.');
                }
            }
        } catch (error) {
            console.error('Error:', error);
            showError('Network error. Please check your connection and try again.');
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = 'Submit Registration';
        }
    });
    
    // Validation functions
    function validateForm() {
        let isValid = true;
        
        // Required fields (including authentication fields)
        const requiredFields = [
            'school_name', 'school_type', 'school_address', 'county_city',
            'school_contact_number', 'school_email', 'owner_full_name',
            'owner_email', 'owner_phone', 'position', 'number_of_students',
            'number_of_teachers', 'username', 'password'
        ];
        
        requiredFields.forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (!field || !field.value.trim()) {
                showFieldError(field, 'This field is required');
                isValid = false;
            } else {
                clearFieldError(field);
            }
        });
        
        // Email validation
        const emailFields = ['school_email', 'owner_email'];
        emailFields.forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field && field.value && !isValidEmail(field.value)) {
                showFieldError(field, 'Please enter a valid email address');
                isValid = false;
            }
        });
        
        // Phone validation (basic)
        const phoneFields = ['school_contact_number', 'owner_phone'];
        phoneFields.forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field && field.value && !isValidPhone(field.value)) {
                showFieldError(field, 'Please enter a valid phone number');
                isValid = false;
            }
        });
        
        // Number validation (allow 0)
        const numberFields = ['number_of_students', 'number_of_teachers'];
        numberFields.forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field && field.value) {
                const value = parseInt(field.value);
                if (isNaN(value) || value < 0) {
                    showFieldError(field, 'Please enter a valid number (minimum 0)');
                    isValid = false;
                }
            }
        });
        
        // Username validation
        const usernameField = form.querySelector('[name="username"]');
        if (usernameField && usernameField.value) {
            if (usernameField.value.length < 3) {
                showFieldError(usernameField, 'Username must be at least 3 characters');
                isValid = false;
            }
        }
        
        // Password validation
        const passwordField = form.querySelector('[name="password"]');
        if (passwordField && passwordField.value) {
            if (passwordField.value.length < 6) {
                showFieldError(passwordField, 'Password must be at least 6 characters');
                isValid = false;
            }
        }
        
        // URL validation (optional field)
        const websiteField = form.querySelector('[name="school_website"]');
        if (websiteField && websiteField.value && !isValidUrl(websiteField.value)) {
            showFieldError(websiteField, 'Please enter a valid URL');
            isValid = false;
        }
        
        return isValid;
    }
    
    function isValidEmail(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    }
    
    function isValidPhone(phone) {
        // Basic phone validation - allows digits, spaces, dashes, parentheses, plus
        const phoneRegex = /^[\d\s\-\+\(\)]+$/;
        return phoneRegex.test(phone) && phone.replace(/\D/g, '').length >= 7;
    }
    
    function isValidUrl(url) {
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    }
    
    function showFieldError(field, message) {
        if (!field) return;
        
        field.classList.add('error');
        const errorSpan = field.parentElement.querySelector('.error-message');
        if (errorSpan) {
            errorSpan.textContent = message;
            errorSpan.style.display = 'block';
        }
    }
    
    function clearFieldError(field) {
        if (!field) return;
        
        field.classList.remove('error');
        const errorSpan = field.parentElement.querySelector('.error-message');
        if (errorSpan) {
            errorSpan.textContent = '';
            errorSpan.style.display = 'none';
        }
    }
    
    function displayServerErrors(errors) {
        // Display server-side validation errors
        Object.keys(errors).forEach(fieldName => {
            const field = form.querySelector(`[name="${fieldName}"]`);
            if (field) {
                const errorMessages = Array.isArray(errors[fieldName]) 
                    ? errors[fieldName].join(', ') 
                    : errors[fieldName];
                showFieldError(field, errorMessages);
            }
        });
        
        // Show general error message
        const generalError = errors.non_field_errors || errors.detail || 'Please correct the errors above.';
        showError(generalError);
    }
    
    function showSuccess(message) {
        formMessages.className = 'form-messages success';
        formMessages.textContent = message;
        formMessages.style.display = 'block';
    }
    
    function showError(message) {
        formMessages.className = 'form-messages error';
        formMessages.textContent = message;
        formMessages.style.display = 'block';
    }
    
    function clearMessages() {
        formMessages.style.display = 'none';
        formMessages.textContent = '';
        formMessages.className = 'form-messages';
    }
    
    // Get CSRF token from cookies
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
    
    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const href = this.getAttribute('href');
            if (href !== '#' && href !== '#login') {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
});

