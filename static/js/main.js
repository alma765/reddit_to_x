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
        setInterval(function() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    // Update status badge
                    const statusBadge = document.querySelector('.card-header .badge');
                    if (statusBadge) {
                        statusBadge.className = `badge bg-${data.status === 'running' ? 'success' : 'danger'}`;
                        statusBadge.textContent = data.status === 'running' ? 'Running' : 'Stopped';
                    }
                    
                    // Update stats
                    const statBoxes = document.querySelectorAll('.stat-box h3');
                    if (statBoxes.length >= 3) {
                        statBoxes[0].textContent = data.total_posts;
                        statBoxes[1].textContent = data.successful_posts;
                        statBoxes[2].textContent = data.failed_posts;
                    }
                    
                    // Update progress bar
                    const progressBar = document.querySelector('.progress-bar');
                    if (progressBar) {
                        progressBar.style.width = `${data.success_rate}%`;
                        progressBar.textContent = `${Math.round(data.success_rate)}%`;
                    }
                })
                .catch(error => console.error('Error fetching status:', error));
        }, 30000); // Refresh every 30 seconds
    }
});
