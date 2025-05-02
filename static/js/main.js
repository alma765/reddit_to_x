// Dashboard update functionality
// Track API request failures to avoid hammering the server
let failedAttempts = 0;
const MAX_FAILED_ATTEMPTS = 3;

// Function to reset the failed attempts counter
function resetFailedAttempts() {
    console.log('Resetting failed attempts counter and resuming normal updates');
    failedAttempts = 0;
    updateDashboardData();
}

// Function to update dashboard data from API
function updateDashboardData() {
    // If we've had too many failed attempts, slow down the refresh rate
    if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
        console.log(`Reached maximum failed attempts (${MAX_FAILED_ATTEMPTS}). Reducing API calls.`);
        setTimeout(resetFailedAttempts, 60000); // Try again after 1 minute
        return;
    }
    
    fetch('/api/status')
        .then(response => {
            if (!response.ok) {
                failedAttempts++;
                throw new Error(`API returned status ${response.status}`);
            }
            // Reset failed attempts counter on success
            failedAttempts = 0;
            return response.json();
        })
        .then(data => {
            // Update status badge
            const statusBadge = document.querySelector('.card-header .badge');
            if (statusBadge) {
                let badgeClass = 'badge bg-';
                let badgeText = '';
                
                switch(data.status) {
                    case 'running':
                        badgeClass += 'success';
                        badgeText = 'Running';
                        break;
                    case 'stopped':
                        badgeClass += 'danger';
                        badgeText = 'Stopped';
                        break;
                    default:
                        badgeClass += 'warning';
                        badgeText = 'Unknown';
                }
                
                statusBadge.className = badgeClass;
                statusBadge.textContent = badgeText;
            }
            
            // Update stats
            const statBoxes = document.querySelectorAll('.stat-box h3');
            if (statBoxes.length >= 4) {
                statBoxes[0].textContent = data.total_posts || 0;
                statBoxes[1].textContent = data.successful_posts || 0;
                statBoxes[2].textContent = data.duplicate_posts || 0;
                statBoxes[3].textContent = (data.failed_posts || 0) - (data.duplicate_posts || 0);
            }
            
            // Update progress bar
            const progressBar = document.querySelector('.progress-bar');
            if (progressBar) {
                const successRate = Math.round(data.success_rate || 0);
                progressBar.style.width = `${successRate}%`;
                progressBar.textContent = `${successRate}%`;
                
                // Update progress bar color based on success rate
                if (successRate >= 70) {
                    progressBar.className = 'progress-bar bg-success';
                } else if (successRate >= 40) {
                    progressBar.className = 'progress-bar bg-warning';
                } else {
                    progressBar.className = 'progress-bar bg-danger';
                }
            }
            
            // Handle Twitter rate limit timer
            const rateLimitAlert = document.getElementById('rate-limit-alert');
            const rateLimitTimer = document.getElementById('rate-limit-timer');
            
            // Update rate limit information if available
            if (data.twitter_rate_limited && rateLimitAlert && rateLimitTimer) {
                // Make sure alert is visible
                rateLimitAlert.style.display = '';
                
                // Update timer if we have expiration info
                if (data.twitter_rate_limit_info && data.twitter_rate_limit_info.minutes_remaining !== undefined) {
                    const minutes = data.twitter_rate_limit_info.minutes_remaining;
                    
                    if (minutes > 0) {
                        // Format as MM:SS
                        const mins = Math.floor(minutes);
                        const secs = Math.round((minutes - mins) * 60);
                        rateLimitTimer.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
                        rateLimitTimer.classList.remove('bg-success');
                        rateLimitTimer.classList.add('bg-danger');
                    } else {
                        // Rate limit has expired
                        rateLimitTimer.textContent = 'Expired';
                        rateLimitTimer.classList.remove('bg-danger');
                        rateLimitTimer.classList.add('bg-success');
                        
                        // Refresh page to apply changes if rate limit expired
                        setTimeout(() => {
                            window.location.reload();
                        }, 5000);
                    }
                } else {
                    // Default to 24-hour limit for the main Twitter daily rate limit
                    rateLimitTimer.textContent = '24:00:00';
                }
            } else if (rateLimitAlert) {
                // Hide alert if not rate limited
                rateLimitAlert.style.display = 'none';
            }
        })
        .catch(error => {
            console.error('Error fetching status:', error);
            // Visual indicator that something went wrong
            const statusBadge = document.querySelector('.card-header .badge');
            if (statusBadge) {
                statusBadge.className = 'badge bg-warning';
                statusBadge.textContent = 'Error';
            }
        });
}

// Initialize on document load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Feather icons
    feather.replace();

    // Add console logging for debugging
    console.log('Page loaded, initializing buttons');

    // Handle Post to Twitter button clicks
    document.querySelectorAll('.post-to-twitter').forEach(button => {
        button.addEventListener('click', async function() {
            const postId = this.dataset.postId;
            const button = this;
            
            // Disable button and show loading state
            button.disabled = true;
            button.innerHTML = '<i data-feather="loader"></i> Posting...';
            feather.replace();
            
            try {
                const response = await fetch(`/posts/${postId}/post-to-twitter`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    // Update button to show success
                    button.innerHTML = '<i data-feather="check-circle"></i> Posted!';
                    feather.replace();
                    
                    // Add Twitter link
                    const twitterLink = document.createElement('a');
                    twitterLink.href = data.twitter_post_url;
                    twitterLink.target = '_blank';
                    twitterLink.className = 'btn btn-success';
                    twitterLink.innerHTML = '<i data-feather="twitter"></i> View on Twitter';
                    feather.replace();
                    
                    // Replace button with link
                    button.parentNode.replaceChild(twitterLink, button);
                } else {
                    // Show error
                    button.innerHTML = '<i data-feather="alert-circle"></i> Error';
                    feather.replace();
                    
                    // Show error message
                    alert(data.error || 'Failed to post to Twitter');
                }
            } catch (error) {
                console.error('Error posting to Twitter:', error);
                button.innerHTML = '<i data-feather="alert-circle"></i> Error';
                feather.replace();
                alert('Failed to post to Twitter. Please try again.');
            }
        });
    });

    // Enable tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    if (typeof bootstrap !== 'undefined') {
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
        
        // Enable popovers
        var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function(popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });
    }
    
    // Auto-dismiss alerts
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-persistent)');
        alerts.forEach(function(alert) {
            if (typeof bootstrap !== 'undefined') {
                var bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } else {
                // Fallback if bootstrap is not available
                alert.style.display = 'none';
            }
        });
    }, 5000);
    
    // Auto-refresh dashboard data
    if (window.location.pathname === '/') {
        // Initial data load
        updateDashboardData();
        
        // Set interval for regular updates - every 30 seconds
        // But use a longer interval (2 minutes) to reduce API load
        setInterval(updateDashboardData, 120000);
    }
});
