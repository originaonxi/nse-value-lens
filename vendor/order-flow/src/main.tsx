import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { UiIconProvider } from '@/assets/svg';
import { installUiTooltips } from '@/lib/uiTooltips';
import { loadUnderlyings } from './lib/underlyings';
import { dismissBootSplash, settleWithin } from './lib/bootstrap';
import '@/styles/oi-design-tokens.css';
import '@/styles/index.css';
import '@/styles/strike-filter.css';
import '@/styles/ui-inputs.css';
import '@/styles/ui-instrument-picker-polish.css';
import '@/styles/ui-cards.css';
import '@/styles/oi-polish.css';
import '@/styles/ui-option-chain-8k.css';
import '@/styles/ui-chart-canvas-8k.css';
import '@/styles/oi-controls.css';
import '@/styles/ui-selection-theme.css';
import '@/styles/option-chain-loading-state.css';
import '@/styles/option-chain-refinement.css';
import '@/styles/ui-market-levels.css';
import '@/styles/ui-strike-payoff.css';
import '@/styles/ui-theme.css';
import '@/styles/ui-chain-prototype-theme.css';
import '@/styles/ui-prototype-system.css';
import '@/styles/ui-chain-approved.css';
import '@/styles/ui-strike-detail-studio.css';
import '@/styles/ui-overlay-panels.css';
import '@/styles/ui-colour-system.css';
import '@/styles/ui-market-semantics.css';
import '@/styles/ui-icons.css';
import '@/styles/ui-brand.css';
import '@/styles/ui-typography.css';
import '@/styles/ui-pixel-clean.css';
import '@/styles/ui-precision-edge.css';
import '@/styles/ui-chain-header-surface.css';
import '@/styles/ui-accordions.css';
import '@/styles/ui-calendar.css';
import '@/styles/ui-chain-expiry-menu.css';
import '@/styles/ui-gaps.css';
import '@/styles/ui-option-chain-focus.css';
import '@/styles/ui-widget-frames.css';
import '@/styles/market-unavailable-state.css';
import '@/styles/option-chain-premium.css';
import '@/styles/ui-index-market-strip.css';
import '@/styles/ui-index-market-strip-theme.css';
import '@/styles/ui-spot-divider-overlay.css';
import '@/styles/ui-columns-panel.css';
import '@/styles/ui-chain-table-header.css';
import '@/styles/ui-chain-grid-finish.css';
import '@/styles/ui-chain-phone-strike.css';
import '@/styles/ui-chain-phone-compact.css';
import '@/styles/ui-segmented-controls.css';
import '@/styles/ui-insight-cards.css';
import '@/styles/ui-insight-phone.css';
import '@/styles/ui-light-surface-authority.css';
import '@/styles/ui-market-line-authority.css';
import '@/styles/ui-chain-no-purple.css';
import '@/styles/ui-motion.css';
import '@/styles/ui-apple-finish.css';
import '@/styles/ui-data-surface-finish.css';
import '@/styles/ui-selection-pills.css';
import '@/styles/ui-chain-selection-header.css';
import '@/styles/ui-chart-controls.css';
import '@/styles/ui-selection-surfaces.css';
import '@/styles/ui-strike-studio-authority.css';
import '@/styles/ui-chart-stage-authority.css';
import '@/styles/ui-strike-chart.css';
import '@/styles/ui-strike-nav.css';
import '@/styles/ui-control-capsule-authority.css';
import '@/styles/ui-phone-polish.css';
import '@/styles/ui-wide-screen.css';
import '@/styles/ui-terminal-refinement.css';
import '@/styles/ui-borders.css';
import '@/styles/website-tool-chrome.css';
import '@/styles/ui-chain-reference-finish.css';
import '@/styles/ui-chain-type.css';
import '@/styles/ui-tool-rhythm.css';
import '@/styles/ui-finish-pass.css';
import '@/styles/ui-box-system.css';
import '@/styles/ui-tooltip.css';
// Last: the mrchartist.com type and colour (fonts, ink, up/down, borders).
import '@/styles/website-brand.css';

// The theme: the reader's saved choice, else light.
let theme: 'light' | 'dark' = 'light';
try {
  const saved = localStorage.getItem('preferredTheme');
  if (saved === 'light' || saved === 'dark') theme = saved;
} catch { /* storage blocked: the system's theme stands */ }
document.documentElement.dataset.theme = theme;
document.documentElement.style.colorScheme = theme;

// The registry is resolved before mounting, but never holds the page hostage.
settleWithin(loadUnderlyings()).finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <UiIconProvider>
        <MemoryRouter initialEntries={['/market-flow']}>
          <App />
        </MemoryRouter>
      </UiIconProvider>
    </StrictMode>,
  );
  dismissBootSplash();
  installUiTooltips();
});
