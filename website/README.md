# Fixer Website (Render)

This folder contains the marketing site for `fixer.gg`.

## Local preview

From repository root:

```powershell
python -m http.server 8080 --directory website
```

Open `http://localhost:8080`.

## Deploy on Render

- This repo includes `render.yaml` configured for a static site.
- Service `rootDir` is set to `website`.
- Attach custom domain `fixer.gg` in Render dashboard.

## AdSense setup

Replace all placeholders below with your real values:
- `ca-pub-9043637540751936` is already set in `website/index.html`
- `pub-9043637540751936` is already set in `website/ads.txt`
- `data-ad-slot` values in `website/index.html`

Then submit `https://fixer.gg/ads.txt` in AdSense if requested.

## SEO checklist

- Set canonical domain in Render and force HTTPS.
- Submit sitemap: `https://fixer.gg/sitemap.xml` in Google Search Console.
- Add Search Console verification meta tag when available.
- Keep `privacy.html` published for ad policy compliance.

