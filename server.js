const express = require('express');
const axios = require('axios');
const app = express();
const PORT = process.env.PORT || 8090;

// Load tokens
let tokens = [];
if (process.env.TOKENS) {
  tokens = process.env.TOKENS.split('\n').map(t => t.trim()).filter(t => t);
} else {
  const fs = require('fs');
  const path = require('path');
  const tokensFile = path.join(__dirname, 'tokens.txt');
  if (fs.existsSync(tokensFile)) {
    tokens = fs.readFileSync(tokensFile, 'utf8')
      .split('\n')
      .map(t => t.trim())
      .filter(t => t.length > 0);
  }
}

if (tokens.length === 0) {
  console.error('❌ ERROR: No tokens! Set TOKENS env var.');
  process.exit(1);
}

// Stats per token
const stats = tokens.map(t => ({ token: t, used: 0, failed: 0 }));
let currentIdx = 0;

function getNextToken() {
  currentIdx = (currentIdx + 1) % tokens.length;
  return stats[currentIdx];
}

app.use(express.json());

// Dashboard.html
app.get('/', (req, res) => {
  const totalUsed = stats.reduce((a, b) => a + b.used, 0);
  const totalFailed = stats.reduce((a, b) => a + b.failed, 0);
  const activeTokens = stats.filter(s => s.failed <= 10).length; // heuristic

  const rows = stats.map((s, i) => `
    <tr>
      <td>${i+1}</td>
      <td><code>${s.token.substring(0,12)}...</code></td>
      <td>${s.used}</td>
      <td>${s.failed}</td>
      <td style="color:${s.failed > 10 ? '#f85149' : '#3fb950'}">${s.failed > 10 ? 'OFF' : 'OK'}</td>
    </tr>
  `).join('');

  const html = `
    <html><body style="background:#0d1117;color:#c9d1d9;font-family:monospace;padding:20px;">
      <h1 style="color:#58a6ff;">⚡️ Ampere Proxy Dashboard</h1>
      <p>Active tokens: <strong style="color:#3fb950;">${activeTokens}/${tokens.length}</strong></p>
      <p>Total requests: <strong>${totalUsed}</strong> (failed: ${totalFailed})</p>
      <table border="1" cellpadding="8" style="border-collapse:collapse;background:#161b22;color:#c9d1d9;">
        <tr style="background:#21262d;">
          <th>#</th><th>Token (first 12 chars)</th><th>Used</th><th>Failed</th><th>Status</th>
        </tr>
        ${rows}
      </table>
      <p style="font-size:12px;color:#8b949e;">Refresh to update</p>
    </body></html>
  `;
  res.send(html);
});

// Proxy endpoint
app.post('/v1/chat/completions', async (req, res) => {
  const stat = getNextToken();
  try {
    const r = await axios.post('https://api.ampere.sh/v1/chat/completions', req.body, {
      headers: { Authorization: `Bearer ${stat.token}` },
      timeout: 60000
    });
    stat.used++;
    res.json(r.data);
  } catch (e) {
    stat.failed++;
    console.error(`❌ Token ${stat.token.substring(0,8)} error: ${e.message}`);
    // Retry once with next token
    try {
      const stat2 = getNextToken();
      const r2 = await axios.post('https://api.ampere.sh/v1/chat/complet
