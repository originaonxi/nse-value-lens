/**
 * Picks the data provider from MF_PROVIDER (default: the demo market).
 * Register a new broker here after copying ./template.mjs.
 */
import { createDemoProvider } from './demo.mjs';
import { createHttpProvider } from './http.mjs';
import { createRecordedProvider } from './recorded.mjs';
import { createTemplateProvider } from './template.mjs';
import { createUpstoxProvider } from './upstox.mjs';

export const PROVIDERS = {
  demo: createDemoProvider,
  recorded: createRecordedProvider,
  archive: universe => createRecordedProvider(universe, {
    id: 'archive',
    dir: 'data/archive',
    dirEnv: 'MF_ARCHIVE_DIR',
    dateEnv: 'MF_ARCHIVE_DATE',
    label: 'NSE archive',
    hint: 'Build one with `npm run fetch:nse`',
  }),
  http: createHttpProvider,
  upstox: createUpstoxProvider,
  template: createTemplateProvider,
};

export function createProvider(universe, id = process.env.MF_PROVIDER || 'demo') {
  const create = PROVIDERS[id];
  if (!create) throw new Error(`Unknown MF_PROVIDER "${id}". Known: ${Object.keys(PROVIDERS).join(', ')}.`);
  return create(universe);
}
