const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const BACKEND_URL = process.env.BACKEND_URL || '';

// Serve static files from public directory
app.use(express.static(path.join(__dirname, 'public')));

// Inject backend URL configuration into HTML
app.get('/', (req, res) => {
    const fs = require('fs');
    const indexPath = path.join(__dirname, 'public', 'index.html');
    
    fs.readFile(indexPath, 'utf8', (err, html) => {
        if (err) {
            return res.status(500).send('Error loading page');
        }
        
        // Inject BACKEND_URL as a global variable before any scripts
        const configScript = `<script>window.BACKEND_URL = '${BACKEND_URL}';</script>`;
        const modifiedHtml = html.replace('<head>', `<head>\n    ${configScript}`);
        
        res.send(modifiedHtml);
    });
});

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
    console.log(`Frontend server running on http://localhost:${PORT}`);
    console.log(`Backend URL configured as: ${BACKEND_URL || '(same origin)'}`);
});
