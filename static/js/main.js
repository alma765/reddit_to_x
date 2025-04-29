// Initialize Feather icons
document.addEventListener('DOMContentLoaded', function() {
    feather.replace();
    
    // Enable tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Enable popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Auto-dismiss alerts
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-persistent)');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // Auto-refresh dashboard data
    if (window.location.pathname === '/') {
        // Initial data load
        updateDashboardData();
        
        // Set interval for regular updates
        setInterval(updateDashboardData, 30000); // Refresh every 30 seconds
    }
    
    // Function to update dashboard data from API
    function updateDashboardData() {
        fetch('/api/status')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`API returned status ${response.status}`);
                }
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
});
