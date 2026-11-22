/**
 * AI Sales Associate - Loader Entrypoint
 * Async lightweight (<15KB) zero-dependency entrypoint.
 * Loads shield, dom_extractor, hesitation_matrix, session_memory, and widget.
 * Guarantees zero Core Web Vitals impact and zero crashes on the host store.
 */

(function (window, document) {
  'use strict';

  // Prevent duplicate execution
  if (window.__AISalesAssociate && window.__AISalesAssociate.isInitialized) {
    return;
  }

  // Detect script origin and configuration
  const currentScript = document.currentScript || (function () {
    const scripts = document.getElementsByTagName('script');
    for (let i = scripts.length - 1; i >= 0; i--) {
      if (scripts[i].src && scripts[i].src.includes('loader.js')) {
        return scripts[i];
      }
    }
    return null;
  })();

  const baseUrl = currentScript && currentScript.src
    ? currentScript.src.substring(0, currentScript.src.lastIndexOf('/') + 1)
    : './';

  const config = {
    backendUrl: (currentScript && typeof currentScript.getAttribute === 'function' && currentScript.getAttribute('data-backend-url')) ||
      (window.__AI_SALES_CONFIG && window.__AI_SALES_CONFIG.backendUrl) ||
      'http://localhost:8000',
    storeName: (currentScript && typeof currentScript.getAttribute === 'function' && currentScript.getAttribute('data-store-name')) || 'Karthik & Co.'
  };

  const MODULES = [
    'shield.js',
    'session_memory.js',
    'dom_extractor.js',
    'hesitation_matrix.js',
    'widget.js'
  ];

  let widgetElement = null;
  let hesitationInstance = null;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.type = 'text/javascript';
      script.async = true;
      script.src = src;
      script.onload = () => resolve();
      script.onerror = (err) => reject(new Error(`Failed to load script: ${src}`));
      document.head.appendChild(script);
    });
  }

  async function bootstrap() {
    try {
      // 1. Load modules sequentially to ensure shield is established first
      for (const mod of MODULES) {
        // Skip if already loaded globally
        if (mod === 'shield.js' && window.__AISalesAssociateShield) continue;
        if (mod === 'session_memory.js' && window.__AISalesAssociateSessionMemory) continue;
        if (mod === 'dom_extractor.js' && window.__AISalesAssociateDOMExtractor) continue;
        if (mod === 'hesitation_matrix.js' && window.__AISalesAssociateHesitationMatrix) continue;
        if (mod === 'widget.js' && window.__AISalesAssociateWidget) continue;

        await loadScript(`${baseUrl}${mod}?v=1.0.2`);
      }

      // 2. Shield wrap bootstrap
      const shield = window.__AISalesAssociateShield;
      const safeExec = shield ? shield.executeSafe.bind(shield) : (fn) => fn();

      safeExec(() => {
        // 3. Extract DOM product data on idle
        const extractor = window.__AISalesAssociateDOMExtractor;
        const memory = window.__AISalesAssociateSessionMemory;

        // 4. Mount Widget Web Component
        const widgetModule = window.__AISalesAssociateWidget;
        if (widgetModule && typeof widgetModule.mount === 'function') {
          widgetElement = widgetModule.mount(document.body, {
            backendUrl: config.backendUrl,
            storeName: config.storeName
          });
        }

        // 5. Connect Extractor to Widget & Session Memory
        if (extractor) {
          extractor.extract((product) => {
            if (product) {
              if (widgetElement && typeof widgetElement.setProductContext === 'function') {
                widgetElement.setProductContext(product);
              }
              if (memory && product.isProductPage) {
                memory.recordProductView(product);
              }
            }
          });

          extractor.onProductChange((updatedProduct) => {
            if (widgetElement && typeof widgetElement.setProductContext === 'function') {
              widgetElement.setProductContext(updatedProduct);
            }
          });
        }

        // 6. Connect Hesitation Matrix to Widget
        const hesitationModule = window.__AISalesAssociateHesitationMatrix;
        if (hesitationModule && typeof hesitationModule.create === 'function') {
          hesitationInstance = hesitationModule.create({
            dwellThresholdMs: 20000,
            cooldownMs: 45000
          });

          hesitationInstance.onHesitation((trigger) => {
            if (widgetElement && typeof widgetElement.handleHesitationTrigger === 'function') {
              widgetElement.handleHesitationTrigger(trigger);
            }
          });
        }
      });
    } catch (error) {
      console.warn('[AI Sales Associate Loader] Non-fatal initialization error:', error);
      if (window.__AISalesAssociateShield) {
        window.__AISalesAssociateShield.recordFailure(error);
      }
    }
  }

  function destroy() {
    try {
      if (hesitationInstance && typeof hesitationInstance.destroy === 'function') {
        hesitationInstance.destroy();
        hesitationInstance = null;
      }
      if (widgetElement && typeof widgetElement.destroy === 'function') {
        widgetElement.destroy();
        widgetElement = null;
      }
      const existingTag = document.querySelector('ai-sales-associate');
      if (existingTag && existingTag.parentNode) {
        existingTag.parentNode.removeChild(existingTag);
      }
    } catch (e) {
      // Safe teardown
    }
  }

  // Public SDK API
  window.__AISalesAssociate = {
    version: '1.0.0',
    isInitialized: true,
    open: () => {
      if (widgetElement && typeof widgetElement.openDrawer === 'function') {
        widgetElement.openDrawer();
      }
    },
    close: () => {
      if (widgetElement && typeof widgetElement.closeDrawer === 'function') {
        widgetElement.closeDrawer();
      }
    },
    toggle: () => {
      if (widgetElement && typeof widgetElement.toggleDrawer === 'function') {
        widgetElement.toggleDrawer();
      }
    },
    sendMessage: (text) => {
      if (widgetElement && typeof widgetElement.handleUserSend === 'function') {
        widgetElement.handleUserSend(text);
      }
    },
    getProductContext: () => {
      return window.__AISalesAssociateDOMExtractor
        ? window.__AISalesAssociateDOMExtractor.getCachedProduct()
        : null;
    },
    destroy: destroy
  };

  // Safe DOM ready trigger
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
  } else {
    // Zero-delay microtask execution if DOM already loaded
    setTimeout(bootstrap, 0);
  }
})(window, document);
