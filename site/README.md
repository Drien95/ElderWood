# Site ElderWood

Site statique (une seule page) qui présente le lore, le règlement, les guides whitelist et les fiches de révision d'ElderWood RP.

- `index.html` : le site généré, prêt à ouvrir dans un navigateur ou à héberger (GitHub Pages, Netlify…).
- `template.html` : la mise en page, les styles et le script (navigation, recherche dans le règlement, ciel étoilé).
- `build.py` : lit `lore/`, `reglement/`, `conseils/` et `revision/` et régénère `index.html`.

## Mettre à jour le contenu

Modifie les fichiers Markdown, puis :

```bash
pip install markdown beautifulsoup4
python3 site/build.py
```

## Mettre en ligne avec GitHub Pages

Settings → Pages → « Deploy from a branch » → branche `main`, dossier `/ (root)`, puis ouvre `/site/`.
(Le dépôt étant privé, GitHub Pages demande un compte payant ; sinon, Netlify ou Cloudflare Pages acceptent le dossier `site/` tel quel.)
