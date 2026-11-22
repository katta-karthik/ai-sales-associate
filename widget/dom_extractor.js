/**
 * AI Sales Associate - DOM Extractor
 * Platform-agnostic product parser reading schema.org application/ld+json,
 * OpenGraph tags, and page meta via requestIdleCallback.
 * Zero impact on Core Web Vitals (LCP, FID/INP, CLS).
 */

(function (window, document) {
  'use strict';

  if (window.__AISalesAssociateDOMExtractor) {
    return;
  }

  const shield = window.__AISalesAssociateShield || {
    executeSafe: (fn, fallback) => {
      try { return fn(); } catch (e) { return fallback; }
    }
  };

  class DOMExtractor {
    constructor() {
      this.cachedProduct = null;
      this.listeners = [];
      this.observer = null;
      this.setupVariantListeners();
    }

    /**
     * Platform-agnostic product extraction scheduled during browser idle periods.
     */
    extract(callback) {
      const scheduleIdle = window.requestIdleCallback || ((cb) => setTimeout(() => cb({ timeRemaining: () => 15 }), 50));

      scheduleIdle(() => {
        shield.executeSafe(() => {
          const product = this._performExtraction();
          this.cachedProduct = product;
          if (typeof callback === 'function') {
            callback(product);
          }
          this._notifyListeners(product);
        });
      }, { timeout: 2000 });
    }

    getCachedProduct() {
      if (!this.cachedProduct) {
        this.cachedProduct = this._performExtraction();
      }
      return this.cachedProduct;
    }

    onProductChange(fn) {
      if (typeof fn === 'function') {
        this.listeners.push(fn);
      }
    }

    _notifyListeners(product) {
      for (const fn of this.listeners) {
        shield.executeSafe(() => fn(product));
      }
    }

    _performExtraction() {
      const jsonLd = this._extractJsonLd();
      const meta = this._extractMetaTags();
      const dom = this._extractDOMHeuristics();

      const title = jsonLd.title || meta.title || dom.title || document.title || 'Featured Apparel';
      const price = jsonLd.price || meta.price || dom.price || '';
      const currency = jsonLd.currency || meta.currency || dom.currency || '$';
      const image = jsonLd.image || meta.image || dom.image || '';
      const description = jsonLd.description || meta.description || dom.description || '';
      const material = jsonLd.material || dom.material || '';
      const brand = jsonLd.brand || meta.brand || dom.brand || 'Karthik & Co.';
      const sku = jsonLd.sku || dom.sku || '';
      const availability = jsonLd.availability || dom.availability || 'InStock';

      const loc = typeof window !== 'undefined' && window.location ? window.location : { pathname: '', href: '' };

      const isProductPage = Boolean(
        jsonLd.isProduct ||
        meta.isProduct ||
        dom.isProduct ||
        document.querySelector('[itemtype*="Product"]') ||
        loc.pathname.includes('/product') ||
        document.querySelector('#add-to-cart, .add-to-cart, button[name="add"]')
      );

      const variants = dom.variants || { sizes: [], colors: [] };
      const selectedVariant = dom.selectedVariant || { size: '', color: '' };
      const ctaButtons = dom.ctaButtons || {};

      return {
        isProductPage,
        id: sku || title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 32),
        name: this._cleanText(title),
        title: this._cleanText(title),
        price: this._cleanPrice(price),
        currency: currency.replace(/USD/i, '$'),
        description: this._cleanText(description),
        material: this._cleanText(material),
        image,
        brand: this._cleanText(brand),
        sku,
        availability,
        variants,
        sizes: variants.sizes || [],
        colors: variants.colors || [],
        selectedVariant,
        ctaButtons,
        url: loc.href
      };
    }

    _extractJsonLd() {
      const result = { isProduct: false };
      try {
        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        for (const script of scripts) {
          try {
            const raw = JSON.parse(script.textContent || '{}');
            const items = Array.isArray(raw) ? raw : (raw['@graph'] ? raw['@graph'] : [raw]);

            for (const item of items) {
              if (item && (item['@type'] === 'Product' || item['@type'] === 'IndividualProduct')) {
                result.isProduct = true;
                result.title = item.name;
                result.description = item.description;
                result.sku = item.sku || item.productID;

                if (item.image) {
                  result.image = Array.isArray(item.image)
                    ? (typeof item.image[0] === 'string' ? item.image[0] : item.image[0]?.url)
                    : (typeof item.image === 'string' ? item.image : item.image?.url);
                }

                if (item.brand) {
                  result.brand = typeof item.brand === 'string' ? item.brand : item.brand.name;
                }

                if (item.offers) {
                  const offer = Array.isArray(item.offers) ? item.offers[0] : item.offers;
                  if (offer) {
                    result.price = offer.price || offer.lowPrice;
                    result.currency = offer.priceCurrency || '$';
                    result.availability = offer.availability ? offer.availability.split('/').pop() : 'InStock';
                  }
                }
                return result;
              }
            }
          } catch (e) {
            // Ignore individual invalid JSON-LD script blocks
          }
        }
      } catch (e) {
        // Ignore
      }
      return result;
    }

    _extractMetaTags() {
      const getMeta = (props) => {
        for (const prop of props) {
          const el = document.querySelector(`meta[property="${prop}"], meta[name="${prop}"]`);
          if (el && el.content) return el.content.trim();
        }
        return null;
      };

      const ogType = getMeta(['og:type']);
      const isProduct = ogType === 'product' || ogType === 'og:product';

      return {
        isProduct,
        title: getMeta(['og:title', 'twitter:title']),
        description: getMeta(['og:description', 'twitter:description', 'description']),
        image: getMeta(['og:image', 'twitter:image', 'image']),
        price: getMeta(['product:price:amount', 'og:price:amount']),
        currency: getMeta(['product:price:currency', 'og:price:currency']),
        brand: getMeta(['product:brand', 'og:site_name'])
      };
    }

    _extractDOMHeuristics() {
      const dom = {
        isProduct: false,
        variants: { sizes: [], colors: [] },
        selectedVariant: { size: '', color: '' },
        ctaButtons: {}
      };

      // Title detection
      const titleEl = document.querySelector('h1.product-title, h1[itemprop="name"], .product-single__title, .product-detail-title, h1');
      if (titleEl) {
        dom.title = titleEl.textContent;
      }

      // Price detection
      const priceEl = document.querySelector('[itemprop="price"], .product-price, .current-price, .price, .product-single__price');
      if (priceEl) {
        dom.price = priceEl.getAttribute('content') || priceEl.textContent;
      }

      // Image detection
      const imageEl = document.querySelector('img[itemprop="image"], .product-image img, .product-featured-image, .main-product-img');
      if (imageEl) {
        dom.image = imageEl.src || imageEl.getAttribute('data-src');
      }

      // Description
      const descEl = document.querySelector('[itemprop="description"], .product-description, .product-detail-description');
      if (descEl) {
        dom.description = descEl.textContent;
      }

      // Material detection
      const materialEl = document.querySelector('[itemprop="material"], .product-material, #acc-body-fabric, #pdp-bullet-points');
      if (materialEl) {
        const text = materialEl.textContent || '';
        const match = text.match(/\b(100%[^\n,.]*|merino wool|wool|linen|cotton|silk|cashmere|leather)[^,.\n]*/i);
        if (match) {
          dom.material = match[0].trim();
        }
      }

      // CTAs
      const addToCartEl = document.querySelector('#add-to-cart, #add-to-cart-btn, .add-to-cart, button[name="add"], .btn-add-to-cart, [data-action="add-to-cart"]');
      if (addToCartEl) {
        dom.isProduct = true;
        dom.ctaButtons.addToCart = addToCartEl.id ? `#${addToCartEl.id}` : '.add-to-cart';
      }

      const buyNowEl = document.querySelector('#buy-now, #buy-now-btn, .buy-now, button[data-action="buy-now"], .shopify-payment-button');
      if (buyNowEl) {
        dom.ctaButtons.buyNow = buyNowEl.id ? `#${buyNowEl.id}` : '.buy-now';
      }

      // Variant detection (Size buttons, swatches, radio inputs, and <select> dropdowns)
      const sizeElements = document.querySelectorAll('.size-option, .size-btn, [data-variant-type="size"], input[name*="size" i], button[data-size]');
      if (sizeElements.length > 0) {
        dom.isProduct = true;
        sizeElements.forEach((el) => {
          const val = el.textContent?.trim() || el.value || el.getAttribute('data-size');
          if (val && !dom.variants.sizes.includes(val)) {
            dom.variants.sizes.push(val);
          }
          if (el.classList.contains('active') || el.classList.contains('selected') || el.checked || el.getAttribute('aria-selected') === 'true') {
            dom.selectedVariant.size = val;
          }
        });
      }

      // Check for <select> size dropdowns (Shopify, WooCommerce, Magento, etc.)
      const sizeSelects = document.querySelectorAll('select[name*="size" i], select#size, select[id*="size" i], select[name="id"]');
      sizeSelects.forEach((sel) => {
        dom.isProduct = true;
        Array.from(sel.options || []).forEach((opt) => {
          const val = (opt.text || opt.value || '').trim();
          if (val && !dom.variants.sizes.includes(val) && !val.toLowerCase().includes('select size') && !val.toLowerCase().includes('choose')) {
            dom.variants.sizes.push(val);
          }
          if (opt.selected && val && !val.toLowerCase().includes('select size')) {
            dom.selectedVariant.size = val;
          }
        });
      });

      const colorElements = document.querySelectorAll('.color-swatch, .color-btn, [data-variant-type="color"], input[name*="color" i], button[data-color]');
      if (colorElements.length > 0) {
        dom.isProduct = true;
        colorElements.forEach((el) => {
          const val = el.getAttribute('title') || el.getAttribute('data-color') || el.value || el.textContent?.trim();
          if (val && !dom.variants.colors.includes(val)) {
            dom.variants.colors.push(val);
          }
          if (el.classList.contains('active') || el.classList.contains('selected') || el.checked) {
            dom.selectedVariant.color = val;
          }
        });
      }

      const colorSelects = document.querySelectorAll('select[name*="color" i], select#color, select[id*="color" i]');
      colorSelects.forEach((sel) => {
        dom.isProduct = true;
        Array.from(sel.options || []).forEach((opt) => {
          const val = (opt.text || opt.value || '').trim();
          if (val && !dom.variants.colors.includes(val) && !val.toLowerCase().includes('select color')) {
            dom.variants.colors.push(val);
          }
          if (opt.selected && val) {
            dom.selectedVariant.color = val;
          }
        });
      });

      return dom;
    }

    setupVariantListeners() {
      // Listen for click/change on variant toggles to keep cached state fresh
      document.addEventListener('click', (e) => {
        const target = e.target.closest('.size-option, .size-btn, button[data-size], .color-swatch, button[data-color]');
        if (target) {
          // Debounce re-extraction
          setTimeout(() => {
            this.extract();
          }, 100);
        }
      }, { passive: true });
    }

    _cleanText(str) {
      if (!str) return '';
      return String(str).replace(/\s+/g, ' ').trim();
    }

    _cleanPrice(str) {
      if (!str) return '';
      const match = String(str).replace(/,/g, '').match(/\d+(\.\d{1,2})?/);
      return match ? match[0] : String(str).trim();
    }
  }

  const extractorInstance = new DOMExtractor();

  window.__AISalesAssociateDOMExtractor = {
    instance: extractorInstance,
    extract: (cb) => extractorInstance.extract(cb),
    getCachedProduct: () => extractorInstance.getCachedProduct(),
    onProductChange: (fn) => extractorInstance.onProductChange(fn)
  };
})(window, document);
