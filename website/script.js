(() => {
  const reveals = document.querySelectorAll('.reveal');

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('in-view');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );

  reveals.forEach((element, index) => {
    element.style.transitionDelay = `${Math.min(index * 80, 360)}ms`;
    observer.observe(element);
  });

  const yearTarget = document.getElementById('copyright');
  if (yearTarget) {
    yearTarget.textContent = `Copyright ${new Date().getFullYear()} Fixer. All rights reserved.`;
  }

  const initAds = () => {
    document.querySelectorAll('.adsbygoogle').forEach((ad) => {
      if (ad.dataset.adInitialized === 'true') return;
      try {
        (window.adsbygoogle = window.adsbygoogle || []).push({});
        ad.dataset.adInitialized = 'true';
      } catch (error) {
        // Keep site functional even if ads are blocked or not yet ready.
      }
    });
  };

  initAds();
  window.addEventListener('load', initAds, { once: true });
  setTimeout(initAds, 1200);
})();
