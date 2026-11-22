/**
 * AI Sales Associate - Shield & Circuit Breaker
 * Guarantees zero crashes on the host store.
 * If errors or unexpected conditions occur, gracefully unmounts without affecting the store.
 */

(function (window) {
  'use strict';

  if (window.__AISalesAssociateShield) {
    return;
  }

  class CircuitBreaker {
    constructor(maxFailures = 3, resetTimeoutMs = 60000) {
      this.maxFailures = maxFailures;
      this.resetTimeoutMs = resetTimeoutMs;
      this.failureCount = 0;
      this.lastFailureTime = null;
      this.isTripped = false;
      this.unmountHandlers = [];
      this.installGlobalSafetyNet();
    }

    registerUnmount(handler) {
      if (typeof handler === 'function') {
        this.unmountHandlers.push(handler);
      }
    }

    recordFailure(error) {
      const now = Date.now();
      if (this.lastFailureTime && now - this.lastFailureTime > this.resetTimeoutMs) {
        this.failureCount = 0;
      }

      this.failureCount++;
      this.lastFailureTime = now;
      console.warn(`[AI Sales Associate Shield] Non-fatal error intercepted (${this.failureCount}/${this.maxFailures}):`, error);

      if (this.failureCount >= this.maxFailures) {
        this.trip();
      }
    }

    recordSuccess() {
      if (this.failureCount > 0 && !this.isTripped) {
        this.failureCount = 0;
      }
    }

    trip() {
      if (this.isTripped) return;
      this.isTripped = true;
      console.warn('[AI Sales Associate Shield] Circuit breaker tripped. Silently unmounting to protect host store.');
      this.unmount();
    }

    unmount() {
      for (const handler of this.unmountHandlers) {
        try {
          handler();
        } catch (e) {
          // Swallow any cleanup errors to protect host
        }
      }
      this.unmountHandlers = [];

      if (window.__AISalesAssociate && typeof window.__AISalesAssociate.destroy === 'function') {
        try {
          window.__AISalesAssociate.destroy();
        } catch (e) {
          // Ignore
        }
      }

      // Remove any lingering widget host element
      try {
        const root = document.querySelector('ai-sales-associate, #ai-sales-associate-root');
        if (root && root.parentNode) {
          root.parentNode.removeChild(root);
        }
      } catch (e) {
        // Ignore
      }
    }

    executeSafe(fn, fallbackValue = null) {
      if (this.isTripped) return fallbackValue;
      try {
        const result = fn();
        this.recordSuccess();
        return result;
      } catch (err) {
        this.recordFailure(err);
        return fallbackValue;
      }
    }

    async executeSafeAsync(asyncFn, fallbackValue = null) {
      if (this.isTripped) return fallbackValue;
      try {
        const result = await asyncFn();
        this.recordSuccess();
        return result;
      } catch (err) {
        this.recordFailure(err);
        return fallbackValue;
      }
    }

    wrap(fn, fallbackValue = null) {
      const self = this;
      return function (...args) {
        if (self.isTripped) return fallbackValue;
        try {
          const result = fn.apply(this, args);
          self.recordSuccess();
          return result;
        } catch (err) {
          self.recordFailure(err);
          return fallbackValue;
        }
      };
    }

    installGlobalSafetyNet() {
      try {
        window.addEventListener('error', (event) => {
          // Only intercept errors originating from widget files
          const filename = event.filename || '';
          if (filename.includes('widget') || filename.includes('loader.js') || filename.includes('ai-sales')) {
            console.warn('[AI Sales Associate Shield] Intercepted widget runtime error:', event.message);
            this.recordFailure(event.error || event.message);
            // Prevent event from bubbling or breaking host store scripts
            if (typeof event.preventDefault === 'function') {
              event.preventDefault();
            }
          }
        }, true);

        window.addEventListener('unhandledrejection', (event) => {
          const reason = String(event.reason || '');
          if (reason.includes('ai-sales') || reason.includes('widget')) {
            console.warn('[AI Sales Associate Shield] Intercepted widget unhandled rejection:', event.reason);
            this.recordFailure(event.reason);
            if (typeof event.preventDefault === 'function') {
              event.preventDefault();
            }
          }
        });
      } catch (e) {
        // Ignore safety net install issues
      }
    }
  }

  const shieldInstance = new CircuitBreaker(3, 60000);

  window.__AISalesAssociateShield = {
    CircuitBreaker,
    instance: shieldInstance,
    executeSafe: (fn, fallback) => shieldInstance.executeSafe(fn, fallback),
    executeSafeAsync: (fn, fallback) => shieldInstance.executeSafeAsync(fn, fallback),
    wrap: (fn, fallback) => shieldInstance.wrap(fn, fallback),
    recordFailure: (err) => shieldInstance.recordFailure(err),
    registerUnmount: (handler) => shieldInstance.registerUnmount(handler),
    unmount: () => shieldInstance.unmount(),
    isTripped: () => shieldInstance.isTripped
  };
})(window);
