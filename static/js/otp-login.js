

document.addEventListener('DOMContentLoaded', function() {
    
    const emailForm = document.getElementById('emailForm');
    const emailInput = document.querySelector('input[name="email"]');
    const sendOtpBtn = document.getElementById('sendOtpBtn');
    const emailError = document.getElementById('emailError');

    if (emailInput && sendOtpBtn) {
        
        emailInput.addEventListener('input', function() {
            const email = this.value.trim();
            const isValid = validateEmail(email);
            
            if (email.length > 0 && !isValid) {
                emailError.textContent = 'Please enter a valid email address';
                sendOtpBtn.disabled = true;
            } else {
                emailError.textContent = '';
                sendOtpBtn.disabled = email.length === 0;
            }
        });

        
        if (emailForm) {
            emailForm.addEventListener('submit', function(e) {
                e.preventDefault();
                
                const email = emailInput.value.trim();
                if (!validateEmail(email)) {
                    emailError.textContent = 'Please enter a valid email address';
                    return;
                }

                
                setButtonLoading(sendOtpBtn, true);
                
                
                this.submit();
            });
        }
    }

    
    const otpInputGroup = document.getElementById('otpInputGroup');
    const otpDigits = document.querySelectorAll('.otp-digit');
    const otpHidden = document.getElementById('otpHidden');
    const otpForm = document.getElementById('otpForm');
    const verifyOtpBtn = document.getElementById('verifyOtpBtn');
    const otpError = document.getElementById('otpError');

    if (otpDigits.length > 0) {
        
        otpDigits[0].focus();

        
        otpDigits.forEach((input, index) => {
            input.addEventListener('input', function(e) {
                const value = this.value;
                
                
                this.value = value.replace(/[^0-9]/g, '');
                
                if (this.value.length === 1) {
                    
                    if (index < otpDigits.length - 1) {
                        otpDigits[index + 1].focus();
                    }
                }
                
                
                updateOtpValue();
                
                
                otpError.textContent = '';
            });

            input.addEventListener('focus', function() {
                this.select();
            });

            input.addEventListener('keydown', function(e) {
                
                if (/^[0-9]$/.test(e.key) && this.value.length === 1) {
                    this.value = '';
                }
                
                if (e.key === 'Backspace' && this.value === '' && index > 0) {
                    otpDigits[index - 1].focus();
                }
                
                
                if (e.key === 'ArrowLeft' && index > 0) {
                    otpDigits[index - 1].focus();
                }
                if (e.key === 'ArrowRight' && index < otpDigits.length - 1) {
                    otpDigits[index + 1].focus();
                }
            });

            
            input.addEventListener('paste', function(e) {
                e.preventDefault();
                const pastedData = e.clipboardData.getData('text').replace(/[^0-9]/g, '');
                
                if (pastedData.length === 4) {
                    otpDigits.forEach((digit, i) => {
                        digit.value = pastedData[i] || '';
                    });
                    updateOtpValue();
                    otpDigits[3].focus();
                }
            });
        });

        
        function updateOtpValue() {
            const otp = Array.from(otpDigits).map(input => input.value).join('');
            if (otpHidden) {
                otpHidden.value = otp;
            }
            
            
            if (verifyOtpBtn) {
                verifyOtpBtn.disabled = otp.length !== 4;
            }
        }

        
        if (otpForm) {
            otpForm.addEventListener('submit', function(e) {
                const otp = otpHidden.value;
                
                if (otp.length !== 4) {
                    e.preventDefault();
                    otpError.textContent = 'Please enter a valid 4-digit OTP';
                    return;
                }

                
                setButtonLoading(verifyOtpBtn, true);
            });
        }
    }

    
    const resendOtpBtn = document.getElementById('resendOtpBtn');
    const countdownSpan = document.getElementById('countdown');
    
    if (resendOtpBtn && countdownSpan) {
        let countdown = 60;
        
        const timer = setInterval(function() {
            countdown--;
            countdownSpan.textContent = countdown;
            
            if (countdown <= 0) {
                clearInterval(timer);
                resendOtpBtn.disabled = false;
                resendOtpBtn.innerHTML = 'Resend OTP';
            }
        }, 1000);

        
        resendOtpBtn.addEventListener('click', function() {
            const emailFormObj = document.getElementById('emailForm');
            if (emailFormObj) {
                resendOtpBtn.disabled = true;
                resendOtpBtn.innerHTML = 'Resending...';
                emailFormObj.submit();
            }
        });
    }

    
    const changeEmailBtn = document.getElementById('changeEmailBtn');
    if (changeEmailBtn) {
        changeEmailBtn.addEventListener('click', function() {
            
            const emailStep = document.getElementById('emailStep');
            const otpStep = document.getElementById('otpStep');
            
            if (emailStep && otpStep) {
                emailStep.style.display = 'block';
                otpStep.style.display = 'none';
                
                
                otpDigits.forEach(input => input.value = '');
                if (otpHidden) otpHidden.value = '';
                
                
                if (emailInput) emailInput.focus();
            } else {
                
                const nextUrl = document.querySelector('input[name="next"]')?.value || '/';
                window.location.href = `${window.location.pathname}?next=${encodeURIComponent(nextUrl)}`;
            }
        });
    }

    
    function validateEmail(email) {
        const re = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
        return re.test(email);
    }

    function setButtonLoading(button, isLoading) {
        if (!button) return;
        
        const btnText = button.querySelector('.btn-text');
        const btnLoader = button.querySelector('.btn-loader');
        
        if (isLoading) {
            button.disabled = true;
            if (btnText) btnText.style.display = 'none';
            if (btnLoader) btnLoader.style.display = 'inline-flex';
        } else {
            button.disabled = false;
            if (btnText) btnText.style.display = 'inline';
            if (btnLoader) btnLoader.style.display = 'none';
        }
    }
});

