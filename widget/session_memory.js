/**
 * AI Sales Associate - Session Memory
 * Preserves thread_id, viewed products, and chat state across page navigations
 * in sessionStorage with memory fallback.
 */

(function (window) {
  'use strict';

  if (window.__AISalesAssociateSessionMemory) {
    return;
  }

  const STORAGE_KEY_PREFIX = '__ai_sales_';

  class SessionMemory {
    constructor() {
      this.inMemoryStore = {};
      this.isStorageAvailable = this._checkStorageAvailability();
      this.threadId = this._initThreadId();
    }

    _checkStorageAvailability() {
      try {
        const testKey = `${STORAGE_KEY_PREFIX}test__`;
        window.sessionStorage.setItem(testKey, '1');
        window.sessionStorage.removeItem(testKey);
        return true;
      } catch (e) {
        return false;
      }
    }

    _getItem(key, fallback = null) {
      const fullKey = `${STORAGE_KEY_PREFIX}${key}`;
      if (this.isStorageAvailable) {
        try {
          const val = window.sessionStorage.getItem(fullKey);
          return val ? JSON.parse(val) : fallback;
        } catch (e) {
          // fallback
        }
      }
      return this.inMemoryStore[fullKey] !== undefined ? this.inMemoryStore[fullKey] : fallback;
    }

    _setItem(key, value) {
      const fullKey = `${STORAGE_KEY_PREFIX}${key}`;
      if (this.isStorageAvailable) {
        try {
          window.sessionStorage.setItem(fullKey, JSON.stringify(value));
          return;
        } catch (e) {
          // fallback to memory
        }
      }
      this.inMemoryStore[fullKey] = value;
    }

    _generateUUID() {
      if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID();
      }
      return 'sales-xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
    }

    _initThreadId() {
      let id = this._getItem('session_id') || this._getItem('thread_id');
      if (!id) {
        id = this._generateUUID();
      }
      this._setItem('session_id', id);
      this._setItem('thread_id', id);
      return id;
    }

    getSessionId() {
      return this.threadId;
    }

    getThreadId() {
      return this.threadId;
    }

    setSessionId(id) {
      if (!id) return;
      this.threadId = id;
      this._setItem('session_id', id);
      this._setItem('thread_id', id);
    }

    recordProductView(product) {
      if (!product || !product.title) return;
      const history = this.getViewedProducts();

      // Deduplicate by id or title
      const existingIdx = history.findIndex((p) => (p.id && p.id === product.id) || p.title === product.title);

      const entry = {
        id: product.id || product.title,
        title: product.title,
        price: product.price,
        currency: product.currency,
        image: product.image,
        url: product.url || (window.location ? window.location.href : ''),
        brand: product.brand,
        selectedVariant: product.selectedVariant || {},
        viewedAt: Date.now()
      };

      if (existingIdx >= 0) {
        history[existingIdx] = entry;
      } else {
        history.unshift(entry);
      }

      // Cap at 10 items
      const capped = history.slice(0, 10);
      this._setItem('viewed_products', capped);
    }

    getViewedProducts() {
      return this._getItem('viewed_products', []);
    }

    getChatHistory() {
      return this._getItem('chat_history', []);
    }

    clearChatHistory() {
      this._setItem('chat_history', []);
      const fullKey = `${STORAGE_KEY_PREFIX}chat_history`;
      if (this.inMemoryStore[fullKey]) {
        delete this.inMemoryStore[fullKey];
      }
    }

    saveChatMessage(msg) {
      const history = this.getChatHistory();
      history.push({
        id: msg.id || this._generateUUID(),
        sender: msg.sender || 'user', // 'user' or 'stylist'
        text: msg.text || '',
        timestamp: msg.timestamp || Date.now(),
        quickReplies: msg.quickReplies || [],
        productRecommendation: msg.productRecommendation || null,
        validationScore: msg.validationScore || null
      });

      // Cap at 30 recent messages
      const capped = history.slice(-30);
      this._setItem('chat_history', capped);
    }

    getIntentStage() {
      return this._getItem('intent_stage', 'EXPLORER');
    }

    setIntentStage(stage) {
      this._setItem('intent_stage', stage);
    }

    getDrawerState() {
      return this._getItem('drawer_state', { isOpen: false, hasOpened: false, bubbleDismissed: false });
    }

    setDrawerState(partialState) {
      const current = this.getDrawerState();
      this._setItem('drawer_state', { ...current, ...partialState });
    }

    recordHesitationSignal(signal) {
      const signals = this._getItem('hesitation_signals', []);
      signals.push({
        ...signal,
        recordedAt: Date.now()
      });
      this._setItem('hesitation_signals', signals.slice(-10));
    }

    getHesitationSignals() {
      return this._getItem('hesitation_signals', []);
    }

    clear() {
      const keys = ['session_id', 'thread_id', 'viewed_products', 'chat_history', 'intent_stage', 'drawer_state', 'hesitation_signals'];
      for (const k of keys) {
        const fullKey = `${STORAGE_KEY_PREFIX}${k}`;
        if (this.isStorageAvailable) {
          try {
            window.sessionStorage.removeItem(fullKey);
          } catch (e) {}
        }
        delete this.inMemoryStore[fullKey];
      }
      this.threadId = this._initThreadId();
    }
  }

  const memoryInstance = new SessionMemory();

  window.__AISalesAssociateSessionMemory = {
    instance: memoryInstance,
    getSessionId: () => memoryInstance.getSessionId(),
    getThreadId: () => memoryInstance.getThreadId(),
    setSessionId: (id) => memoryInstance.setSessionId(id),
    recordProductView: (p) => memoryInstance.recordProductView(p),
    getViewedProducts: () => memoryInstance.getViewedProducts(),
    getChatHistory: () => memoryInstance.getChatHistory(),
    saveChatMessage: (m) => memoryInstance.saveChatMessage(m),
    getIntentStage: () => memoryInstance.getIntentStage(),
    setIntentStage: (s) => memoryInstance.setIntentStage(s),
    getDrawerState: () => memoryInstance.getDrawerState(),
    setDrawerState: (s) => memoryInstance.setDrawerState(s),
    recordHesitationSignal: (s) => memoryInstance.recordHesitationSignal(s),
    getHesitationSignals: () => memoryInstance.getHesitationSignals(),
    clear: () => memoryInstance.clear()
  };
})(window);
