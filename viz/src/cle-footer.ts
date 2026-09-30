/**
 * Center for Land Economics footer + Substack subscribe modal.
 *
 * The footer is the site's quiet funnel: CLE logo → landeconomics.org,
 * "Land is a big deal" → in-page Substack subscribe (iframe modal, no new
 * tab), and a smaller advocacy reach-out mailto. Import and call
 * initCleFooter() on any page that should carry it; openSubscribeModal()
 * is exported separately so other CTAs (e.g. in the app sidebar) can open
 * the same modal.
 *
 * Subscribe-success detection mirrors the landeconomics.org implementation:
 * the sandboxed Substack iframe either fires a second `load` (internal
 * navigation to its confirmation page) or posts a message from
 * *.substack.com after the XHR submit — both are treated as success.
 */

const SUBSTACK_EMBED_URL = 'https://progressandpoverty.substack.com/embed';
const CONTACT_EMAIL = 'greg@landeconomics.org';

// Styled with the AVL GO tokens from design-system.css (every page that loads this footer also
// loads that stylesheet): a light footer with a top border, and an AVL GO dialog for the modal.
const STYLES = `
.cle-footer {
  margin-top: 32px;
  background: var(--avl-bg-surface);
  color: var(--avl-text-body);
  border-top: 1px solid var(--avl-border);
  padding: 40px var(--app-gutter, 16px) 24px;
  font-family: var(--avl-font-sans);
  font-size: var(--avl-text-sm);
  line-height: var(--avl-lh-sm);
}
.cle-footer__inner {
  max-width: calc(var(--avl-container) - 2 * var(--app-gutter, 16px));
  margin: 0 auto;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 32px 48px;
}
.cle-footer__brand img { height: 32px; width: auto; display: block; margin-bottom: 12px; }
.cle-footer__brand p {
  margin: 0;
  color: var(--avl-text-body);
  line-height: var(--avl-leading-relaxed);
  max-width: 40ch;
}
.cle-footer__brand a.cle-footer__site {
  display: block;
  width: fit-content;
  margin-top: 10px;
  color: var(--avl-link);
  font-weight: var(--font-medium);
  text-decoration: none;
}
.cle-footer__brand a.cle-footer__site:hover { color: var(--avl-link-hover); text-decoration: underline; }
.cle-footer__cta h3 {
  margin: 0 0 8px;
  font-family: var(--avl-font-display);
  font-size: var(--avl-text-2xl);
  line-height: var(--avl-lh-2xl);
  font-weight: var(--font-semibold);
  color: var(--avl-text-strong);
}
.cle-footer__cta p {
  margin: 0 0 16px;
  color: var(--avl-text-body);
  line-height: var(--avl-leading-relaxed);
  max-width: 48ch;
}
.cle-footer__subscribe {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--avl-accent);
  border-radius: var(--avl-radius-lg);
  background: var(--avl-accent);
  color: var(--avl-on-accent);
  font-family: inherit;
  font-weight: var(--font-medium);
  font-size: var(--avl-text-sm);
  line-height: var(--avl-lh-sm);
  padding: 8px 20px;
  cursor: pointer;
  transition: background-color var(--transition-fast), border-color var(--transition-fast);
}
.cle-footer__subscribe:hover { background: var(--avl-accent-hover); border-color: var(--avl-accent-hover); }
.cle-footer__cta .cle-footer__advocacy {
  max-width: none;
  margin: 16px 0 0;
  font-size: var(--avl-text-xs);
  line-height: var(--avl-lh-xs);
  color: var(--avl-text-muted);
}
.cle-footer__advocacy a,
.cle-footer__bottom a { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
.cle-footer__advocacy a:hover,
.cle-footer__bottom a:hover { color: var(--avl-text-label); }
.cle-footer__bottom {
  max-width: calc(var(--avl-container) - 2 * var(--app-gutter, 16px));
  margin: 32px auto 0;
  padding-top: 16px;
  border-top: 1px solid var(--avl-border);
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
  justify-content: space-between;
  font-size: var(--avl-text-xs);
  line-height: var(--avl-lh-xs);
  color: var(--avl-text-muted);
}

.cle-subscribe-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: var(--avl-overlay);
  animation: fadeIn var(--transition-fast);
}
.cle-subscribe-dialog {
  position: relative;
  width: 100%;
  max-width: 28rem;
  max-height: 90vh;
  overflow-y: auto;
  background: var(--avl-bg-surface);
  color: var(--avl-text-body);
  border: 1px solid var(--avl-border);
  border-radius: var(--avl-radius-xl);
  padding: 24px;
  box-shadow: var(--avl-shadow-xl);
  font-family: var(--avl-font-sans);
  font-size: var(--avl-text-sm);
  line-height: var(--avl-lh-sm);
}
.cle-subscribe-dialog .cle-kicker {
  margin: 0 0 4px;
  font-size: var(--avl-text-xs);
  line-height: var(--avl-lh-xs);
  font-weight: var(--font-semibold);
  letter-spacing: var(--avl-tracking-label);
  text-transform: uppercase;
  color: var(--avl-link);
}
.cle-subscribe-dialog h2 {
  margin: 0 0 6px;
  padding-right: 32px;
  font-size: var(--avl-text-xl);
  line-height: var(--avl-lh-xl);
  font-weight: var(--font-bold);
  color: var(--avl-text-strong);
}
.cle-subscribe-dialog .cle-sub { margin: 0 0 16px; color: var(--avl-text-body); line-height: var(--avl-leading-relaxed); }
.cle-subscribe-dialog iframe {
  display: block;
  width: 100%;
  height: 320px;
  border: 1px solid var(--avl-border);
  border-radius: var(--avl-radius-lg);
  background: #ffffff; /* the Substack embed is always light */
}
.cle-subscribe-close {
  position: absolute;
  right: 12px;
  top: 12px;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--avl-radius-lg);
  background: transparent;
  color: var(--avl-text-faint);
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
  transition: color var(--transition-fast), background-color var(--transition-fast);
}
.cle-subscribe-close:hover { background: var(--avl-bg-muted); color: var(--avl-text-body); }
.cle-subscribe-thanks {
  display: flex; align-items: center; gap: 10px; margin: 8px 0 4px;
  font-size: var(--avl-text-lg); line-height: var(--avl-lh-lg); font-weight: var(--font-semibold); color: var(--avl-text-strong);
}
.cle-subscribe-thanks .tick {
  width: 32px; height: 32px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--avl-success-bg); color: var(--avl-success-text);
  border: 1px solid var(--avl-success-border); font-size: 16px;
}
`;

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  stylesInjected = true;
  const style = document.createElement('style');
  style.textContent = STYLES;
  document.head.appendChild(style);
}

export function openSubscribeModal(): void {
  injectStyles();

  const overlay = document.createElement('div');
  overlay.className = 'cle-subscribe-overlay';
  overlay.setAttribute('role', 'presentation');
  overlay.innerHTML = `
    <div class="cle-subscribe-dialog" role="dialog" aria-modal="true" aria-labelledby="cle-subscribe-heading">
      <button type="button" class="cle-subscribe-close" aria-label="Close">&#215;</button>
      <p class="cle-kicker">Progress and Poverty</p>
      <h2 id="cle-subscribe-heading">Subscribe to Progress and Poverty</h2>
      <p class="cle-sub">Writing on land value taxes, housing, and political economy from the Center for Land Economics.</p>
      <iframe
        src="${SUBSTACK_EMBED_URL}"
        title="Subscribe to Progress and Poverty"
        scrolling="no"
        sandbox="allow-scripts allow-forms allow-same-origin"
      ></iframe>
    </div>
  `;

  const dialog = overlay.querySelector('.cle-subscribe-dialog') as HTMLElement;
  const iframe = overlay.querySelector('iframe') as HTMLIFrameElement;
  const closeBtn = overlay.querySelector('.cle-subscribe-close') as HTMLButtonElement;

  const prevOverflow = document.body.style.overflow;
  document.body.style.overflow = 'hidden';

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    document.body.style.overflow = prevOverflow;
    document.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('message', onMessage);
    overlay.remove();
  };

  let submitted = false;
  const markSubmitted = () => {
    if (submitted) return;
    submitted = true;
    dialog.innerHTML = `
      <button type="button" class="cle-subscribe-close" aria-label="Close">&#215;</button>
      <p class="cle-kicker">Progress and Poverty</p>
      <div class="cle-subscribe-thanks"><span class="tick">&#10003;</span> Thanks for subscribing!</div>
      <p class="cle-sub">Check your inbox for a confirmation email from Substack.</p>
    `;
    (dialog.querySelector('.cle-subscribe-close') as HTMLButtonElement).addEventListener('click', close);
    window.setTimeout(close, 2500);
  };

  // Signal A: a second iframe load = Substack navigated to its confirmation page.
  let initialLoadSeen = false;
  iframe.addEventListener('load', () => {
    if (!initialLoadSeen) { initialLoadSeen = true; return; }
    markSubmitted();
  });

  // Signal B: Substack posts a message after a successful XHR submit.
  const onMessage = (event: MessageEvent) => {
    if (typeof event.origin !== 'string' || !event.origin.includes('substack.com')) return;
    if (event.source !== iframe.contentWindow) return;
    markSubmitted();
  };
  window.addEventListener('message', onMessage);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
  };
  document.addEventListener('keydown', onKeyDown);

  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  closeBtn.addEventListener('click', close);

  document.body.appendChild(overlay);
  closeBtn.focus();
}

export function initCleFooter(): void {
  injectStyles();

  const footer = document.createElement('footer');
  footer.className = 'cle-footer';
  footer.innerHTML = `
    <div class="cle-footer__inner">
      <div class="cle-footer__brand">
        <a href="https://landeconomics.org" target="_blank" rel="noopener" aria-label="Center for Land Economics">
          <img class="only-light" src="/cle-logo-2color.svg" alt="Center for Land Economics" width="190" height="32">
          <img class="only-dark" src="/cle-logo-white.svg" alt="Center for Land Economics" width="190" height="32">
        </a>
        <p>The Center for Land Economics conducts research and provides education to promote equitable assessments and foster sustainable development.</p>
        <a class="cle-footer__site" href="https://landeconomics.org" target="_blank" rel="noopener">landeconomics.org &rarr;</a>
        <a class="cle-footer__site" href="https://github.com/Center-for-Land-Economics/civicmapper" target="_blank" rel="noopener">Civic Mapper is open source &mdash; GitHub &rarr;</a>
      </div>
      <div class="cle-footer__cta">
        <h3>Land is a big deal.</h3>
        <p>To understand what these maps mean for housing, taxes, and your city&rsquo;s future, subscribe to Progress and Poverty &mdash; our writing on land value taxes, housing, and political economy.</p>
        <button type="button" class="cle-footer__subscribe" data-cle-subscribe>Subscribe</button>
        <p class="cle-footer__advocacy">Interested in land value tax advocacy where you live? <a href="mailto:${CONTACT_EMAIL}?subject=Land%20value%20tax%20advocacy">Reach out</a>.</p>
      </div>
    </div>
    <div class="cle-footer__bottom">
      <span>&copy; ${new Date().getFullYear()} Center for Land Economics &middot; Civic Mapper is a CLE project</span>
      <span>
        <a href="https://progressandpoverty.substack.com" target="_blank" rel="noopener">Substack</a>
        &nbsp;&middot;&nbsp;
        <a href="https://putitonamap.com" target="_blank" rel="noopener">Put It On A Map</a>
        &nbsp;&middot;&nbsp;
        <a href="https://givebutter.com/wK8u7p" target="_blank" rel="noopener">Donate</a>
        &nbsp;&middot;&nbsp;
        <a href="mailto:${CONTACT_EMAIL}">Contact</a>
      </span>
    </div>
  `;

  footer.querySelector('[data-cle-subscribe]')?.addEventListener('click', openSubscribeModal);
  document.body.appendChild(footer);
}
