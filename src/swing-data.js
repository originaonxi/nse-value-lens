'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const {validSnapshot: validVcp} = require('../public/vcp');
const cache = new Map(), inflight = new Map();
async function loadSwing(name) {
  if (!['swing_desk','swing_evidence','expanded_research','cross_asset_research','futures_research','research_data_audit','indicator_research','hhhl_scan','hhhl_refresh_status','vcp_scan','vcp_refresh_status'].includes(name)) throw new Error('Unknown swing dataset');
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
          (name === 'vcp_scan' ? !validVcp(payload) : name === 'hhhl_scan' ? !(payload.universe_count === 200 && Array.isArray(payload.rows) && payload.rows.length === 200 && new Set(payload.rows.map(r=>r.symbol)).size === 200 && payload.market) : name.endsWith('_refresh_status') ? !(['fresh','partial','waiting','failed'].includes(payload.state) && payload.run_id && payload.attempted_at) : name === 'swing_desk' ? !Array.isArray(payload.candidates) : name === 'research_data_audit' ? !Number.isFinite(payload.opening_bars) : !payload.results))
        throw new Error('Invalid upstream dataset');
      source = 'github';
    } catch {
      payload = existing?.payload || JSON.parse(await fs.readFile(path.join(__dirname,'..','public','data',name+'.json'),'utf8'));
      source = 'local-fallback';
    }
    const result = {payload, source, expires:Date.now()+(source==='github'?(/^(hhhl|vcp)_/.test(name)?60000:300000):30000)};
    cache.set(name,result);
    return result;
  })();
  inflight.set(name,request);
  try { return await request; } finally { inflight.delete(name); }
}
module.exports = {loadSwing};
