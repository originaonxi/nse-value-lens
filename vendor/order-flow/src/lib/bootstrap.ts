/** Let startup continue after a failed or hung catalogue read, without keeping
 * a timeout alive after a successful read. */
export async function settleWithin<T>(work: Promise<T>, timeoutMs = 4000): Promise<T | undefined> {
  let timeout: number | undefined;
  try {
    return await Promise.race([
      work.catch(() => undefined),
      new Promise<undefined>(resolve => { timeout = window.setTimeout(resolve, timeoutMs); }),
    ]);
  } finally {
    window.clearTimeout(timeout);
  }
}

/** Reveal the committed interface promptly; a first visit has no artificial
 * minimum wait. Keep the small fade, and honour reduced motion. */
export function dismissBootSplash() {
  const splash = document.getElementById('ui-boot');
  if (!splash) return;
  const remove = () => {
    splash.remove();
    document.getElementById('ui-boot-style')?.remove();
  };
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    remove();
    return;
  }
  requestAnimationFrame(() => requestAnimationFrame(() => {
    splash.classList.add('is-leaving');
    setTimeout(remove, 200);
  }));
}
