/**
 * Cinematic Animation Layer for NewsAnalyzer
 * 負責渲染虛擬滑鼠、點擊漣漪、聚光燈、提示氣泡與標題橫幅
 */
(function () {
  if (window.CinemaOverlay) return;

  class OverlayController {
    constructor() {
      this.speed = 1.0;
      this.paused = false;
      this.isInteractive = false;
      this.cursorX = 100;
      this.cursorY = 100;
      this._initDOM();
    }

    _initDOM() {
      if (document.getElementById('cinema-overlay')) return;

      const overlay = document.createElement('div');
      overlay.id = 'cinema-overlay';
      overlay.innerHTML = `
        <div class="cinema-spotlight-box" id="cinema-spotlight"></div>
        <div class="cinema-cursor" id="cinema-cursor"></div>
        <div class="cinema-tooltip" id="cinema-tooltip"></div>
        <div class="cinema-banner" id="cinema-banner">
          <div class="cinema-banner-title" id="cinema-banner-title"></div>
          <div class="cinema-banner-desc" id="cinema-banner-desc"></div>
        </div>
      `;
      document.body.appendChild(overlay);

      this.cursor = document.getElementById('cinema-cursor');
      this.tooltip = document.getElementById('cinema-tooltip');
      this.banner = document.getElementById('cinema-banner');
      this.bannerTitle = document.getElementById('cinema-banner-title');
      this.bannerDesc = document.getElementById('cinema-banner-desc');
      this.spotlight = document.getElementById('cinema-spotlight');

      // 初始化滑鼠位置在螢幕中央上方
      this.cursorX = window.innerWidth / 2;
      this.cursorY = 180;
      this.updateCursorPos(this.cursorX, this.cursorY, false);
    }

    updateCursorPos(x, y, animate = true) {
      this.cursorX = x;
      this.cursorY = y;
      if (!animate) {
        this.cursor.style.transition = 'none';
      } else {
        this.cursor.style.transition = `transform ${0.45 / this.speed}s cubic-bezier(0.22, 1, 0.36, 1)`;
      }
      this.cursor.style.transform = `translate3d(${x}px, ${y}px, 0)`;

      // 工具提示氣泡同步跟隨滑鼠
      this.tooltip.style.left = `${x}px`;
      this.tooltip.style.top = `${y}px`;
    }

    async moveTo(targetOrX, y = null, duration = 450) {
      let destX = targetOrX;
      let destY = y;

      if (typeof targetOrX === 'string') {
        const el = document.querySelector(targetOrX);
        if (el) {
          const rect = el.getBoundingClientRect();
          destX = rect.left + rect.width / 2;
          destY = rect.top + rect.height / 2;
        } else {
          return;
        }
      }

      this.updateCursorPos(destX, destY, true);
      await this.sleep((duration / this.speed));
    }

    async click(target = null) {
      if (target) {
        await this.moveTo(target);
      }
      this.cursor.classList.add('clicking');
      this._createRipple(this.cursorX, this.cursorY);

      await this.sleep(120 / this.speed);
      this.cursor.classList.remove('clicking');
      await this.sleep(100 / this.speed);
    }

    _createRipple(x, y) {
      const ripple = document.createElement('div');
      ripple.className = 'cinema-ripple';
      ripple.style.left = `${x}px`;
      ripple.style.top = `${y}px`;
      ripple.style.width = '32px';
      ripple.style.height = '32px';
      document.getElementById('cinema-overlay').appendChild(ripple);

      setTimeout(() => ripple.remove(), 700);
    }

    showSpotlight(target) {
      const el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el) {
        this.hideSpotlight();
        return;
      }
      const rect = el.getBoundingClientRect();
      const pad = 8;
      this.spotlight.style.left = `${Math.max(0, rect.left - pad)}px`;
      this.spotlight.style.top = `${Math.max(0, rect.top - pad)}px`;
      this.spotlight.style.width = `${rect.width + pad * 2}px`;
      this.spotlight.style.height = `${rect.height + pad * 2}px`;
      this.spotlight.classList.add('active');
    }

    hideSpotlight() {
      this.spotlight.classList.remove('active');
    }

    showTooltip(text) {
      if (!text) {
        this.hideTooltip();
        return;
      }
      this.tooltip.textContent = text;
      this.tooltip.classList.add('active');
    }

    hideTooltip() {
      this.tooltip.classList.remove('active');
    }

    async showBanner(title, desc = '', duration = 2500) {
      this.bannerTitle.textContent = title;
      this.bannerDesc.textContent = desc;
      this.banner.classList.add('show');

      if (duration > 0) {
        await this.sleep(duration / this.speed);
        this.banner.classList.remove('show');
      }
    }

    hideBanner() {
      this.banner.classList.remove('show');
    }

    async typeText(target, text, charDelay = 30) {
      const el = typeof target === 'string' ? document.querySelector(target) : target;
      if (!el) return;

      await this.moveTo(target);
      await this.click();
      el.focus();
      el.value = '';

      for (let i = 0; i < text.length; i++) {
        while (this.paused) await this.sleep(100);
        el.value += text[i];
        el.dispatchEvent(new Event('input', { bubbles: true }));
        await this.sleep(charDelay / this.speed);
      }
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    sleep(ms) {
      return new Promise(resolve => setTimeout(resolve, Math.max(10, ms)));
    }
  }

  window.CinemaOverlay = new OverlayController();
})();
