'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const cache = new Map(), inflight = new Map();
async function loadSwing(name) {
  if (!['swing_desk','swing_evidence'].includes(name)) throw new Error('Unknown swing dataset');
  const existing = cache.get(name);
  if (existing && existing.expires > Date.now()) return existing;
  if (inflight.has(name)) return inflight.get(name);
  const request = (async () => {
    let payload, source;
    try {
      const res = await fetch('https://raw.githubusercontent.com/originaonxi/nse-value-lens/master/docs/'+name+'.json',
        {signal: AbortSignal.timeout(5000)});
      if (!res.ok) throw new Error('Upstream HTTP '+res.status);
      payload = await res.json();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.as_of || '') ||
          (name === 'swing_desk' ? !Array.isArray(payload.candidates) : !payload.results))
        throw new Error('Invalid upstream dataset');
      source = 'github';
    } catch {
      payload = existing?.payload || JSON.parse(await fs.readFile(path.join(__dirname,'..','public','data',name+'.json'),'utf8'));
      source = 'local-fallback';
    }
    const result = {payload, source, expires:Date.now()+(source==='github'?300000:30000)};
    cache.set(name,result);
    return result;
  })();
  inflight.set(name,request);
  try { return await request; } finally { inflight.delete(name); }
}
module.exports = {loadSwing};
