

document.addEventListener('DOMContentLoaded', function() {
    
    const phoneInput = document.querySelector('input[name="phone"]');
    if (phoneInput) {
        
        phoneInput.addEventListener('input', function(e) {
            
            let value = this.value;
            
            this.value = value.replace(/[^0-9+\s\-()]/g, '');
        });

        
        phoneInput.addEventListener('keypress', function(e) {
            const char = String.fromCharCode(e.which);
            const allowedChars = /[0-9+\s\-()]/;
            
            if (!allowedChars.test(char)) {
                e.preventDefault();
                return false;
            }
        });

        
        phoneInput.addEventListener('paste', function(e) {
            e.preventDefault();
            const pastedText = (e.clipboardData || window.clipboardData).getData('text');
            
            const cleanedText = pastedText.replace(/[^0-9+\s\-()]/g, '');
            
            const start = this.selectionStart;
            const end = this.selectionEnd;
            const before = this.value.substring(0, start);
            const after = this.value.substring(end);
            this.value = before + cleanedText + after;
            
            
            this.selectionStart = this.selectionEnd = start + cleanedText.length;
        });
    }

    
    const pincodeInput = document.querySelector('input[name="pincode"]');
    if (pincodeInput) {
        
        pincodeInput.addEventListener('input', function(e) {
            
            let value = this.value;
            
            this.value = value.replace(/[^0-9\s\-]/g, '');
        });

        
        pincodeInput.addEventListener('keypress', function(e) {
            const char = String.fromCharCode(e.which);
            const allowedChars = /[0-9\s\-]/;
            
            if (!allowedChars.test(char)) {
                e.preventDefault();
                return false;
            }
        });

        
        pincodeInput.addEventListener('paste', function(e) {
            e.preventDefault();
            const pastedText = (e.clipboardData || window.clipboardData).getData('text');
            
            const cleanedText = pastedText.replace(/[^0-9\s\-]/g, '');
            
            const start = this.selectionStart;
            const end = this.selectionEnd;
            const before = this.value.substring(0, start);
            const after = this.value.substring(end);
            this.value = before + cleanedText + after;
            
            
            this.selectionStart = this.selectionEnd = start + cleanedText.length;
        });
    }

    
    [phoneInput, pincodeInput].forEach(input => {
        if (input) {
            input.addEventListener('change', function() {
                const fieldName = this.name === 'phone' ? 'Phone' : 'PIN Code';
                const hasDisallowedChars = this.dataset.lastLength && 
                    this.dataset.lastLength > this.value.length;
                
                this.dataset.lastLength = this.value.length;
            });
        }
    });
});
