/**
 * AI Sales Associate - Hesitation Matrix
 * Behavioral hesitation detector tracking dwell spikes (>20s),
 * scroll reversals, variant toggling, and return-to-top.
 * 100% passive listeners, zero impact on Core Web Vitals (INP/FID, CLS).
 */

(function (window, document) {
  'use strict';

  if (window.__AISalesAssociateHesitationMatrix) {
    return;
  }

  const shield = window.__AISalesAssociateShield || {
    executeSafe: (fn) => { try { return fn(); } catch (e) {} }
  };

  class HesitationMatrix {
    constructor(options = {}) {
      this.dwellThresholdMs = options.dwellThresholdMs || 20000; // 20s dwell spike
      this.cooldownMs = options.cooldownMs || 45000; // Cooldown between proactive nudges
      this.listeners = [];
      this.firedTriggers = new Set();
      this.lastTriggerTime = 0;
      this.startTime = Date.now();
      this.dwellTimer = null;
      this.isDestroyed = false;

      // Scroll tracking
      this.lastScrollY = window.scrollY || window.pageYOffset || 0;
      this.lastScrollDir = null; // 'down' or 'up'
      this.scrollReversals = 0;
      this.reversalResetTimer = null;
      this.maxScrollDepth = 0;

      // Variant toggle tracking
      this.variantClicks = [];

      this.boundScrollHandler = this.onScroll.bind(this);
      this.boundClickHandler = this.onClick.bind(this);
      this.boundVisibilityHandler = this.onVisibilityChange.bind(this);

      this.init();
    }

    init() {
      shield.executeSafe(() => {
        this.startDwellTracking();
        if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
          window.addEventListener('scroll', this.boundScrollHandler, { passive: true });
        }
        if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
          document.addEventListener('click', this.boundClickHandler, { passive: true });
          document.addEventListener('visibilitychange', this.boundVisibilityHandler, { passive: true });
        }
      });
    }

    onHesitation(callback) {
      if (typeof callback === 'function') {
        this.listeners.push(callback);
      }
    }

    emitHesitation(trigger) {
      if (this.isDestroyed) return;
      const now = Date.now();

      // Respect global nudge cooldown
      if (now - this.lastTriggerTime < this.cooldownMs) {
        return;
      }

      // Prevent duplicate triggers of the same type within session
      if (this.firedTriggers.has(trigger.type)) {
        return;
      }

      this.firedTriggers.add(trigger.type);
      this.lastTriggerTime = now;

      const payload = {
        ...trigger,
        timestamp: now,
        dwellSeconds: Math.round((now - this.startTime) / 1000)
      };

      for (const listener of this.listeners) {
        shield.executeSafe(() => listener(payload));
      }
    }

    startDwellTracking() {
      if (this.dwellTimer) clearTimeout(this.dwellTimer);

      this.dwellTimer = setTimeout(() => {
        shield.executeSafe(() => {
          if (document.visibilityState === 'visible' && !this.isDestroyed) {
            this.emitHesitation({
              type: 'DWELL_SPIKE',
              confidence: 0.85,
              reason: 'Customer lingering on product page for over 20 seconds without checkout action.',
              suggestedNudge: "Loving this style? Let me know if you'd like a personal fit or styling recommendation!"
            });
          }
        });
      }, this.dwellThresholdMs);
    }

    onScroll() {
      if (this.isDestroyed) return;
      const currentScrollY = window.scrollY || window.pageYOffset || 0;
      const delta = currentScrollY - this.lastScrollY;

      // Filter tiny jitter scrolls (< 40px)
      if (Math.abs(delta) < 40) return;

      const currentDir = delta > 0 ? 'down' : 'up';
      const docHeight = Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
        document.body.offsetHeight,
        document.documentElement.offsetHeight,
        document.body.clientHeight,
        document.documentElement.clientHeight
      ) - window.innerHeight;

      const scrollDepthPct = docHeight > 0 ? (currentScrollY / docHeight) * 100 : 0;
      if (scrollDepthPct > this.maxScrollDepth) {
        this.maxScrollDepth = scrollDepthPct;
      }

      // Check for Scroll Reversal (e.g. down -> up -> down in quick succession)
      if (this.lastScrollDir && this.lastScrollDir !== currentDir) {
        this.scrollReversals++;

        if (this.reversalResetTimer) clearTimeout(this.reversalResetTimer);
        this.reversalResetTimer = setTimeout(() => {
          this.scrollReversals = 0;
        }, 12000);

        if (this.scrollReversals >= 3) {
          this.emitHesitation({
            type: 'SCROLL_REVERSAL',
            confidence: 0.89,
            reason: 'Frequent scroll direction reversals detected (evaluating sizing, reviews, or materials).',
            suggestedNudge: "Looking for customer reviews or fit details? I can summarize customer fit feedback for you!"
          });
          this.scrollReversals = 0;
        }
      }

      // Check for Return to Top after deep scroll (> 60% down, then back to < 20%)
      if (this.maxScrollDepth >= 60 && scrollDepthPct <= 20 && currentDir === 'up') {
        this.emitHesitation({
          type: 'RETURN_TO_TOP',
          confidence: 0.92,
          reason: 'Shopper read page details/reviews and returned to top without adding to cart.',
          suggestedNudge: "Ready to pick this up? I can help you select the exact right size or check active promos!"
        });
        // Reset depth tracking after trigger
        this.maxScrollDepth = 0;
      }

      this.lastScrollY = currentScrollY;
      this.lastScrollDir = currentDir;
    }

    onClick(e) {
      if (this.isDestroyed) return;
      // Check if user clicked a variant selector (size button, color swatch, etc.)
      const isVariant = e.target.closest('.size-option, .size-btn, button[data-size], .color-swatch, button[data-color], [data-variant-type]');
      if (isVariant) {
        const now = Date.now();
        this.variantClicks.push(now);

        // Filter clicks older than 15s
        this.variantClicks = this.variantClicks.filter((t) => now - t <= 15000);

        if (this.variantClicks.length >= 3) {
          this.emitHesitation({
            type: 'VARIANT_TOGGLE',
            confidence: 0.96,
            reason: 'Rapid switching between sizes/colors indicating sizing or styling uncertainty.',
            suggestedNudge: "Debating between sizes? Tell me how you like your shirts to fit (tailored or relaxed) and I'll pick your ideal fit!"
          });
          this.variantClicks = [];
        }
      }
    }

    onVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        if (this.dwellTimer) clearTimeout(this.dwellTimer);
      } else {
        this.startDwellTracking();
      }
    }

    destroy() {
      this.isDestroyed = true;
      if (this.dwellTimer) clearTimeout(this.dwellTimer);
      if (this.reversalResetTimer) clearTimeout(this.reversalResetTimer);
      if (typeof window !== 'undefined' && typeof window.removeEventListener === 'function') {
        window.removeEventListener('scroll', this.boundScrollHandler);
      }
      if (typeof document !== 'undefined' && typeof document.removeEventListener === 'function') {
        document.removeEventListener('click', this.boundClickHandler);
        document.removeEventListener('visibilitychange', this.boundVisibilityHandler);
      }
      this.listeners = [];
    }
  }

  window.__AISalesAssociateHesitationMatrix = {
    HesitationMatrix,
    create: (options) => new HesitationMatrix(options)
  };
})(window, document);
