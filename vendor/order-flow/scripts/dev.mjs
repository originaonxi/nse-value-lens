/** `npm run dev`: the API (server/index.mjs) and Vite together; Vite proxies data to the API. */
import { spawn } from 'node:child_process';

const run = (cmd, args) => spawn(cmd, args, { stdio: 'inherit', shell: process.platform === 'win32' });
// `npm run dev:recorded` replays a recorded real session instead of the demo market.
const api = run(process.execPath, ['server/index.mjs', ...process.argv.slice(2)]);
const web = run(process.platform === 'win32' ? 'npx.cmd' : 'npx', ['vite']);
const stop = () => { api.kill(); web.kill(); process.exit(); };
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
api.on('exit', code => { if (code) { console.error(`API exited (${code})`); web.kill(); process.exit(code); } });
web.on('exit', code => { api.kill(); process.exit(code ?? 0); });
