import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SymbolMark, symbolMonogram } from './SymbolMark';

describe('symbolMonogram', () => {
  it('curates the index series, whose initials alone would collide', () => {
    expect(symbolMonogram('NIFTY')).toBe('NF');
    expect(symbolMonogram('BANKNIFTY')).toBe('BN');
    expect(symbolMonogram('FINNIFTY')).toBe('FN');
    expect(symbolMonogram('NIFTYNXT50')).toBe('N5');
    expect(symbolMonogram('SENSEX')).toBe('SX');
    expect(symbolMonogram('SENSEX50')).toBe('S5');
  });
  it('derives a stock mark from the symbol itself, case and punctuation aside', () => {
    expect(symbolMonogram('RELIANCE')).toBe('RE');
    expect(symbolMonogram('tcs')).toBe('TC');
    expect(symbolMonogram('M&M')).toBe('MM');
    expect(symbolMonogram('360ONE')).toBe('36');
  });
  it('never renders an empty mark', () => {
    expect(symbolMonogram('')).toBe('—');
    expect(symbolMonogram('!!')).toBe('—');
  });
});

describe('SymbolMark', () => {
  it('names the instrument for a screen reader and separates index from stock', () => {
    const { rerender, container } = render(<SymbolMark symbol="NIFTY" kind="index" />);
    expect(screen.getByRole('img', { name: 'NIFTY' })).toBeVisible();
    expect(container.querySelector('.ui-symbol-mark')).toHaveClass('is-index');
    expect(screen.getByRole('img', { name: 'NIFTY' })).toHaveTextContent('NF');

    rerender(<SymbolMark symbol="RELIANCE" kind="stock" />);
    expect(container.querySelector('.ui-symbol-mark')).toHaveClass('is-stock');
  });
  it('keeps the monogram behind supplied artwork as its fallback', () => {
    const { container } = render(<SymbolMark symbol="TCS" src="/brand/tcs.svg" />);
    expect(container.querySelector('.ui-symbol-mark__art')).toHaveAttribute('src', '/brand/tcs.svg');
    expect(container.querySelector('.ui-symbol-mark__text')).toHaveTextContent('TC');
  });

  it('keeps the monogram showing until the artwork has loaded, and after it fails', () => {
    const { container } = render(<SymbolMark symbol="TCS" src="/brand/tcs.svg" />);
    const mark = container.querySelector('.ui-symbol-mark');
    expect(mark).not.toHaveClass('has-art');
    fireEvent.load(container.querySelector('.ui-symbol-mark__art')!);
    expect(mark).toHaveClass('has-art');
    fireEvent.error(container.querySelector('.ui-symbol-mark__art')!);
    expect(mark).not.toHaveClass('has-art');
    expect(container.querySelector('.ui-symbol-mark__text')).toHaveTextContent('TC');
  });
});
