// Theme toggle — persists to localStorage
window.dash_clientside = Object.assign({}, window.dash_clientside, {
    theme: {
        toggle: function(n_clicks) {
            if (!n_clicks) {
                // On load, apply saved theme
                var saved = localStorage.getItem('dashboard-theme') || 'dark';
                document.documentElement.setAttribute('data-theme', saved);
                return saved === 'light' ? 'Dark Mode' : 'Light Mode';
            }
            var current = document.documentElement.getAttribute('data-theme') || 'dark';
            var next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('dashboard-theme', next);

            // Swap AG Grid theme class on all grids
            document.querySelectorAll('.ag-theme-alpine-dark, .ag-theme-alpine').forEach(function(el) {
                el.classList.remove('ag-theme-alpine-dark', 'ag-theme-alpine');
                el.classList.add(next === 'dark' ? 'ag-theme-alpine-dark' : 'ag-theme-alpine');
            });

            return next === 'light' ? 'Dark Mode' : 'Light Mode';
        }
    }
});

// Apply saved theme on page load
(function() {
    var saved = localStorage.getItem('dashboard-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
})();
