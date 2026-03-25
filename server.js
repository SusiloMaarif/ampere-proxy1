const express = require('express');
const axios = require('axios');
const app = express();

const PORT = process.env.PORT || 8090;

let tokens = (process.env.TOKENS || '').split('\n').filter(t => t.trim());
if (tokens.length === 0) {
  console.error('❌ ERROR: No tokens! Set TOKENS env var.');
  process.exit(1);
}
console.log(`✅ Loaded ${tokens.length} tokens`);

let i = 0;
function getNextToken() { return tokens[i++ % tokens.length]; }

app.use(express.json());
app.get('/', (req, res) => res.json({ status: 'ok', tokens: tokens.length }));
app.post('/v1/chat/completions', async (req, res) => {
  try {
    const r = await axios.post('https://api.ampere.sh/v1/chat/completions', req.body, {
      headers: { Authorization: `Bearer ${getNextToken()}` },
      timeout: 60000
    });
    res.json(r.data);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});
app.get('/health', (req, res) => res.json({ status: 'ok', tokens: tokens.length }));

app.listen(PORT, '0.0.0.0', () => console.log(`⚡️ Proxy on port ${PORT}`));
