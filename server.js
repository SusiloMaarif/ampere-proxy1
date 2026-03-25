const express = require('express');
const axios = require('axios');
const app = express();

const PORT = process.env.PORT || 8090;

// Debug: print raw TOKENS env
console.log('=== DEBUG START ===');
console.log('Raw process.env.TOKENS:', process.env.TOKENS ? process.env.TOKENS.substring(0, 200) : 'undefined');
console.log('==================');

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

console.log('✅ Parsed tokens count:', tokens.length);
if (tokens.length === 0) {
  console.error('❌ ERROR: No tokens! Set TOKENS env var.');
  process.exit(1);
}

let i = 0;
function getNextToken() { return tokens[i++ % tokens.length]; }

app.use(express.json());

app.get('/', (req, res) => {
  res.json({ status: 'ok', tokens: tokens.length, currentIndex: i });
});

app.post('/v1/chat/completions', async (req, res) => {
  try {
    const token = getNextToken();
    const r = await axios.post('https://api.ampere.sh/v1/chat/completions', req.body, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 60000
    });
    res.json(r.data);
  } catch (e) {
    console.error('❌ Proxy error:', e.message);
    res.status(500).json({ error: e.message });
  }
});

app.get('/health', (req, res) => res.json({ status: 'ok', tokens: tokens.length }));

app.listen(PORT, '0.0.0.0', () => {
  console.log(`⚡️ Proxy running on port ${PORT}`);
});
