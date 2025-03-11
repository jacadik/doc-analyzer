/**
 * Document Analyzer - Main JavaScript
 * Contains common functionality used across the application
 */

// Wait for the DOM to be fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Update processing status in footer
    updateProcessingStatus();
    
    // Set interval to update processing status every 5 seconds
    setInterval(updateProcessingStatus, 5000);
    
    // Initialize tooltips
    initTooltips();
    
    // Handle document list search
    initDocumentSearch();
    
    // Handle form range inputs
    syncRangeInputs();
    
    // Handle auto-refresh for processing documents
    setupAutoRefresh();
});

/**
 * Fetch and update processing status in the footer
 */
function updateProcessingStatus() {
    fetch('/api/status')
        .then(response => response.json())
        .then(data => {
            const statusElement = document.getElementById('processing-status');
            if (!statusElement) return;
            
            let statusHtml = '';
            if (data.processing > 0 || data.queue_length > 0) {
                statusHtml = `<span class="spinner-border spinner-border-sm text-primary" role="status"></span> Processing ${data.processing} document(s), ${data.queue_length} in queue`;
            } else {
                statusHtml = `${data.processed}/${data.total} documents processed`;
                if (data.error > 0) {
                    statusHtml += `, ${data.error} with errors`;
                }
            }
            
            statusElement.innerHTML = statusHtml;
        })
        .catch(error => console.error('Error fetching status:', error));
}

/**
 * Initialize Bootstrap tooltips
 */
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

/**
 * Initialize document search functionality
 */
function initDocumentSearch() {
    const documentSearch = document.getElementById('documentSearch');
    if (!documentSearch) return;
    
    const documentRows = document.querySelectorAll('table tbody tr');
    
    documentSearch.addEventListener('input', function() {
        const searchTerm = documentSearch.value.toLowerCase();
        
        documentRows.forEach(row => {
            const fileNameCell = row.querySelector('td:first-child');
            if (!fileNameCell) return;
            
            const fileName = fileNameCell.textContent.toLowerCase();
            if (fileName.includes(searchTerm)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    });
}

/**
 * Sync range inputs with their numeric counterparts
 */
function syncRangeInputs() {
    // Find all pairs of range inputs and their numeric counterparts
    document.querySelectorAll('input[type="range"]').forEach(rangeInput => {
        const id = rangeInput.id;
        if (!id.endsWith('_range')) return;
        
        const baseId = id.replace('_range', '');
        const numericInput = document.getElementById(baseId);
        if (!numericInput) return;
        
        // Sync range to numeric
        rangeInput.addEventListener('input', function() {
            numericInput.value = rangeInput.value;
        });
        
        // Sync numeric to range
        numericInput.addEventListener('input', function() {
            rangeInput.value = numericInput.value;
        });
    });
}

/**
 * Setup auto-refresh for processing documents
 */
function setupAutoRefresh() {
    // Check if we're on a document view page with a processing document
    const isProcessingElement = document.getElementById('isProcessingDocument');
    if (!isProcessingElement) return;
    
    const isProcessing = isProcessingElement.value === 'true';
    if (isProcessing) {
        // Refresh the page every 5 seconds
        setTimeout(function() {
            window.location.reload();
        }, 5000);
    }
}

/**
 * Format file size in a human-readable format
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted file size
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Escape HTML special characters in a string
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    return text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Show confirmation dialog
 * @param {string} message - Confirmation message
 * @param {Function} callback - Function to call if confirmed
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

/**
 * Show a notification message
 * @param {string} message - Message to display
 * @param {string} type - Message type (success, danger, warning, info)
 * @param {number} duration - Duration in milliseconds
 */
function showNotification(message, type = 'info', duration = 3000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show notification-toast`;
    notification.setAttribute('role', 'alert');
    
    // Add message and close button
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Add to container or create one
    let container = document.querySelector('.notification-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'notification-container';
        document.body.appendChild(container);
    }
    
    // Add notification to container
    container.appendChild(notification);
    
    // Auto-remove after duration
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, duration);
}

/**
 * Find text differences between two strings
 * @param {string} text1 - First text
 * @param {string} text2 - Second text
 * @returns {string} HTML with highlighted differences
 */
function findTextDifferences(text1, text2) {
    // Split into words
    const words1 = text1.split(/\s+/);
    const words2 = text2.split(/\s+/);
    
    // Initialize LCS matrix
    const matrix = Array(words1.length + 1).fill().map(() => Array(words2.length + 1).fill(0));
    
    // Build LCS matrix
    for (let i = 1; i <= words1.length; i++) {
        for (let j = 1; j <= words2.length; j++) {
            if (words1[i - 1] === words2[j - 1]) {
                matrix[i][j] = matrix[i - 1][j - 1] + 1;
            } else {
                matrix[i][j] = Math.max(matrix[i - 1][j], matrix[i][j - 1]);
            }
        }
    }
    
    // Reconstruct the diff
    const diff1 = [];
    const diff2 = [];
    let i = words1.length;
    let j = words2.length;
    
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && words1[i - 1] === words2[j - 1]) {
            diff1.unshift({ text: words1[i - 1], added: false, removed: false });
            diff2.unshift({ text: words2[j - 1], added: false, removed: false });
            i--;
            j--;
        } else if (j > 0 && (i === 0 || matrix[i][j - 1] >= matrix[i - 1][j])) {
            diff2.unshift({ text: words2[j - 1], added: true, removed: false });
            j--;
        } else if (i > 0 && (j === 0 || matrix[i][j - 1] < matrix[i - 1][j])) {
            diff1.unshift({ text: words1[i - 1], added: false, removed: true });
            i--;
        }
    }
    
    // Generate HTML
    let html = '<div class="diff-container">';
    
    // First text
    html += '<div class="diff diff-left">';
    diff1.forEach(part => {
        if (part.removed) {
            html += `<span class="diff-removed">${escapeHtml(part.text)}</span> `;
        } else {
            html += `<span class="diff-same">${escapeHtml(part.text)}</span> `;
        }
    });
    html += '</div>';
    
    // Second text
    html += '<div class="diff diff-right">';
    diff2.forEach(part => {
        if (part.added) {
            html += `<span class="diff-added">${escapeHtml(part.text)}</span> `;
        } else {
            html += `<span class="diff-same">${escapeHtml(part.text)}</span> `;
        }
    });
    html += '</div>';
    
    html += '</div>';
    
    return html;
}
