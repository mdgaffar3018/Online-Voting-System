// VoteSecure — Client-Side JavaScript

document.addEventListener('DOMContentLoaded', () => {
    initNavbar();
    initOTPInputs();
    initFlashAutoClose();
    initThemeToggle();
});

// ==================== NAVBAR ====================
function initNavbar() {
    const toggle = document.getElementById('nav-toggle');
    const menu = document.getElementById('nav-menu');
    
    if (toggle && menu) {
        toggle.addEventListener('click', () => {
            menu.classList.toggle('active');
            toggle.classList.toggle('active');
        });
        
        // Close menu when clicking a link
        menu.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', () => {
                menu.classList.remove('active');
                toggle.classList.remove('active');
            });
        });
    }
    
    // Navbar scroll effect
    window.addEventListener('scroll', () => {
        const navbar = document.getElementById('main-navbar');
        if (navbar) {
            navbar.classList.toggle('scrolled', window.scrollY > 50);
        }
    });
}

// ==================== OTP INPUTS ====================
function initOTPInputs() {
    const otpInputs = document.querySelectorAll('.otp-digit');
    const hiddenInput = document.getElementById('otp-hidden');
    
    if (otpInputs.length === 0) return;
    
    otpInputs.forEach((input, index) => {
        input.addEventListener('input', (e) => {
            const value = e.target.value;
            
            // Only allow digits
            if (!/^\d*$/.test(value)) {
                e.target.value = '';
                return;
            }
            
            if (value.length === 1) {
                input.classList.add('filled');
                // Move to next
                if (index < otpInputs.length - 1) {
                    otpInputs[index + 1].focus();
                }
            }
            
            updateHiddenOTP(otpInputs, hiddenInput);
        });
        
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace' && !input.value && index > 0) {
                otpInputs[index - 1].focus();
                otpInputs[index - 1].value = '';
                otpInputs[index - 1].classList.remove('filled');
                updateHiddenOTP(otpInputs, hiddenInput);
            }
        });
        
        // Handle paste
        input.addEventListener('paste', (e) => {
            e.preventDefault();
            const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
            
            pasted.split('').forEach((char, i) => {
                if (otpInputs[i]) {
                    otpInputs[i].value = char;
                    otpInputs[i].classList.add('filled');
                }
            });
            
            if (pasted.length > 0) {
                const focusIndex = Math.min(pasted.length, otpInputs.length - 1);
                otpInputs[focusIndex].focus();
            }
            
            updateHiddenOTP(otpInputs, hiddenInput);
        });
    });
    
    // Focus first input
    otpInputs[0].focus();
}

function updateHiddenOTP(inputs, hidden) {
    if (hidden) {
        hidden.value = Array.from(inputs).map(i => i.value).join('');
    }
}

// ==================== FLASH AUTO-CLOSE ====================
function initFlashAutoClose() {
    const flashes = document.querySelectorAll('.flash-msg');
    flashes.forEach((flash, i) => {
        setTimeout(() => {
            flash.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
            flash.style.opacity = '0';
            flash.style.transform = 'translateX(40px)';
            setTimeout(() => flash.remove(), 400);
        }, 4000 + i * 500);
    });
}

// ==================== PASSWORD TOGGLE ====================
function togglePassword(fieldId) {
    const field = document.getElementById(fieldId);
    if (field) {
        field.type = field.type === 'password' ? 'text' : 'password';
    }
}

// ==================== THEME TOGGLE ====================
function initThemeToggle() {
    const toggleBtn = document.getElementById('theme-toggle');
    if (!toggleBtn) return;
    
    toggleBtn.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
    });
}
