#!/usr/bin/env python3
"""Génère site/index.html à partir des fichiers Markdown du dépôt.

Usage :
    pip install markdown beautifulsoup4
    python3 site/build.py                 # écrit site/index.html
    python3 site/build.py --fragment X    # écrit aussi une version sans <head> (aperçu Artifact)

Le site est une seule page statique : aucun serveur, aucune étape de build côté hébergeur.
Relancer le script après chaque modification de lore/, reglement/ ou conseils/.
"""
import re
import sys
import unicodedata
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, NavigableString

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

HOUSE_KEYS = {
    "aerwyn": ["Aerwyn", "Caerwyn", "Ephyr", "Flux Bleu"],
    "brumval": ["Brumval", "Hearthbane", "Valdorn", "Flux Vert"],
    "falcon": ["Falcon", "Valemont", "Aetherion", "Flux Orange"],
    "venatrix": ["Venatrix", "Dravenholt", "Akkorokamui", "Flux Violet"],
}

# ---------------------------------------------------------------- pages
# route, groupe, onglet, fichier, surtitre, titre
LORE = [
    ("magie", "La Magie", "lore/01-magie.md", "Les fondements du monde", "La Magie"),
    ("ecole", "Elderwood", "lore/02-ecole.md", "L'école", "Elderwood"),
    ("societe", "Société Magique", "lore/03-societe-magique.md", "Au-delà des murs", "La Société Magique"),
    ("contexte", "Contexte", "lore/04-contexte-chronologie.md", "Il était une fois", "Chronologie"),
    ("glossaire", "Glossaire", "lore/05-glossaire.md", "Les mots du monde", "Glossaire"),
    ("creatures", "Entités magiques", "lore/06-creatures.md", "Les êtres du monde", "Entités magiques"),
]
REGLES = [
    ("general", "Général", "reglement/01-general.md"),
    ("vocal", "Vocal", "reglement/02-vocal.md"),
    ("lexique", "Lexique RP", "reglement/03-lexique-rp.md"),
    ("roleplay", "RolePlay", "reglement/04-roleplay.md"),
    ("rpk", "RPK On", "reglement/05-rpk-on.md"),
    ("familles", "Familles", "reglement/06-familles.md"),
]
WL = [
    ("whitelist", "Guide officiel", "conseils/whitelist.md", "Préparer sa candidature", "Guide de la Whitelist"),
    ("whitelist-aide", "Aide rapide", "conseils/whitelist-aide-douane.md", "L'essentiel en dix questions", "Aide Whitelist"),
    ("whitelist-faq", "FAQ", "conseils/whitelist-faq-douane.md", "Questions fréquentes", "FAQ Whitelist"),
    ("creation", "Créer son personnage", None, "Les règles essentielles", "Créer son personnage"),
]


def slug(text):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def house_of(text):
    for key, words in HOUSE_KEYS.items():
        if any(w in text for w in words):
            return key
    return None


def md_to_soup(text):
    # Une liste collée à un paragraphe (sans ligne vide) n'est pas reconnue par Markdown.
    lines, out = text.split("\n"), []
    for i, line in enumerate(lines):
        if re.match(r"^\s*([-*]|\d+\.) ", line) and out and out[-1].strip() and not re.match(
            r"^\s*([-*]|\d+\.) ", out[-1]
        ):
            out.append("")
        out.append(line)
    html = markdown.markdown("\n".join(out), extensions=["extra", "sane_lists", "nl2br"])
    return BeautifulSoup(html, "html.parser")


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def strip_intro(soup):
    """Retire le titre H1, la note de source et le paragraphe d'introduction. Les renvoie."""
    source, lead = None, None
    h1 = soup.find("h1")
    if h1:
        h1.decompose()
    first = soup.find(True, recursive=False)
    if first and first.name == "blockquote":
        source = first.get_text(" ", strip=True)
        first.decompose()
        first = soup.find(True, recursive=False)
    if first and first.name == "p":
        lead = first.decode_contents()
        first.decompose()
    # « Contenu maintenu par le pôle Lore. », signature DouaneAPP
    for p in soup.find_all("p"):
        if "pôle Lore" in p.get_text() or "Whitelist Système" in p.get_text():
            p.decompose()
    return source, lead


def sections(soup, level="h2"):
    """Découpe une soupe en blocs [(titre, [nœuds])] selon un niveau de titre."""
    blocks, current = [], (None, [])
    for node in list(soup.children):
        if isinstance(node, NavigableString) and not node.strip():
            continue
        if getattr(node, "name", None) == level:
            if current[0] is not None or current[1]:
                blocks.append(current)
            current = (node, [])
        else:
            current[1].append(node)
    if current[0] is not None or current[1]:
        blocks.append(current)
    return blocks


def html_of(nodes):
    return "".join(str(n) for n in nodes)


# ---------------------------------------------------------------- transformations

def enhance_lists(frag):
    """Listes « **Nom** (étiquette) : texte » → cartes ; dates → frise."""
    soup = BeautifulSoup(frag, "html.parser")
    for ul in soup.find_all("ul"):
        items = ul.find_all("li", recursive=False)
        if not items:
            continue
        parsed = []
        for li in items:
            strong = li.find("strong")
            if not strong or li.contents[0] is not strong:
                parsed = None
                break
            rest = "".join(str(c) for c in li.contents[1:]).strip()
            m = re.match(r"^(?:\((.*?)\))?\s*:\s*(.*)$", rest, re.S)
            if not m:
                parsed = None
                break
            parsed.append((strong.get_text(), m.group(1), m.group(2)))
        if not parsed:
            continue
        if all(re.match(r"^\d{4}", name) for name, _, _ in parsed):
            new = ['<ol class="timeline">']
            for name, _, desc in parsed:
                year, _, title = name.partition(" — ")
                new.append(
                    f'<li><span class="tl-year">{year}</span><h4>{title}</h4><p>{desc}</p></li>'
                )
            new.append("</ol>")
        elif all(tag is None for _, tag, _ in parsed):
            new = ['<dl class="terms">']
            for name, _, desc in parsed:
                new.append(f'<div class="term"><dt>{name}</dt><dd>{desc}</dd></div>')
            new.append("</dl>")
        else:
            new = ['<div class="places">']
            for name, tag, desc in parsed:
                h = house_of(desc + (tag or ""))
                cls = f" h-{h}" if h and "Salle commune" in (tag or "") else ""
                pill = f'<span class="pill">{tag}</span>' if tag else ""
                new.append(f'<div class="place{cls}">{pill}<h4>{name}</h4><p>{desc}</p></div>')
            new.append("</div>")
        ul.replace_with(BeautifulSoup("".join(new), "html.parser"))
    return str(soup)


def render_entries(nodes, route):
    """Sous-sections H3 → cartes, colorées selon la maison concernée."""
    frag = BeautifulSoup(html_of(nodes), "html.parser")
    blocks = sections(frag, "h3")
    intro, entries, events = "", [], []
    for head, body in blocks:
        if head is None:
            intro += enhance_lists(html_of(body))
            continue
        title = head.get_text()
        body_html = enhance_lists(html_of(body))
        if route == "whitelist-faq":
            q = re.sub(r"^[✦\s]+", "", title)
            entries.append(f'<details class="faq"><summary>{q}</summary><div class="entry-body">{body_html}</div></details>')
            continue
        m = re.match(r"^(\d{4}(?:-\d{4})?) — (.*)$", title)
        if m:  # événements récents de la chronologie
            events.append(
                f'<li class="tl-now"><span class="tl-year">{m.group(1)}</span>'
                f"<h4>{m.group(2)}</h4>{body_html}</li>"
            )
            continue
        name, _, sub = title.partition(" — ")
        h = house_of(title) if route != "whitelist" else None
        cls = f" h-{h}" if h else ""
        sub_html = f'<p class="entry-sub">{sub}</p>' if sub else ""
        entries.append(
            f'<article class="entry{cls}"><h3>{name}</h3>{sub_html}<div class="entry-body">{body_html}</div></article>'
        )
    if events:
        intro = intro.replace("</ol>", "".join(events) + "</ol>", 1)
    if not entries:
        return intro
    if route == "whitelist-faq":
        return intro + '<div class="faqs">' + "".join(entries) + "</div>"
    short = all(len(e) < 2600 for e in entries) and len(entries) >= 2
    grid = " grid" if short else ""
    if route == "ecole" and len(entries) == 4:
        grid = " grid houses-grid"
    return intro + f'<div class="entries{grid}">' + "".join(entries) + "</div>"


LEADS = {
    "whitelist-faq": "Les réponses de l'équipe aux questions qui reviennent le plus : ouverture des WL, âge du personnage, IA, Dissonants, fratries, candidatures à plusieurs et installation du jeu.",
}


def render_page(route, md_text, kicker, title, lead_override=None):
    soup = md_to_soup(md_text)
    source, lead = strip_intro(soup)
    lead = lead_override or lead or LEADS.get(route)
    panels, toc = [], []
    for head, body in sections(soup, "h2"):
        if head is None:
            panels.append(f'<section class="panel">{render_entries(body, route)}</section>')
            continue
        text = head.get_text()
        clean = re.sub(r"^[⬩➤✦\s]+", "", text)
        clean = re.sub(r"^ElderWood - ", "", clean)
        if route == "contexte" and clean.startswith("Créer votre personnage"):
            panels.append(
                '<section class="panel panel-link"><h2>Créer votre personnage</h2>'
                "<p>Les règles essentielles de création (catalyseur, noblesse, Dissonants, filiation, "
                'famille…) sont regroupées dans l\'espace Whitelist.</p>'
                '<p><a class="btn" href="#creation">Lire les règles de création</a></p></section>'
            )
            continue
        sid = f"{route}-{slug(clean)}"
        toc.append((sid, clean))
        panels.append(
            f'<section class="panel" id="{sid}"><h2>{clean}</h2>{render_entries(body, route)}</section>'
        )
    return hero(kicker, title, lead, route, source) + toc_html(toc) + "".join(panels)


def hero(kicker, title, lead, route, source=None):
    src = ""
    if source and not source.startswith("Recopié"):
        src = f'<p class="hero-src">{re.sub(r"Recopié fidèlement.?", "", source).strip()}</p>'
    lead_html = f'<p class="hero-lead">{lead}</p>' if lead else ""
    return (
        f'<header class="hero hero-{route}"><div class="hero-art" aria-hidden="true"></div>'
        f'<p class="kicker">{kicker}</p><h1>{title}</h1>{lead_html}{src}</header>'
    )


def toc_html(toc):
    if len(toc) < 3:
        return ""
    chips = "".join(f'<button type="button" class="chip" data-jump="{sid}">{t}</button>' for sid, t in toc)
    return f'<nav class="toc" aria-label="Sur cette page"><span>Sur cette page</span>{chips}</nav>'


def render_creation():
    md_text = read("lore/04-contexte-chronologie.md")
    part = md_text.split("## Créer votre personnage — les règles essentielles", 1)[1]
    part = part.split("*Contenu maintenu", 1)[0]
    soup = md_to_soup(part)
    cards = []
    principle = ""
    for p in soup.find_all("p"):
        strong = p.find("strong")
        if not strong:
            continue
        name = strong.get_text()
        strong.decompose()
        body = p.decode_contents().strip()
        body = re.sub(r"^(<br/?>\s*)+", "", body).replace("[EWRP],", "").strip()
        if name == "Principe général":
            principle = body
            continue
        cards.append(f'<article class="entry"><h3>{name}</h3><div class="entry-body"><p>{body}</p></div></article>')
    reminders = (
        '<section class="panel"><h2>À retenir pour la whitelist</h2><ul class="checks">'
        "<li>Un personnage humain, âgé de 15 ans à son entrée à Elderwood.</li>"
        "<li>Le format Prénom Nom, original et crédible.</li>"
        "<li>Pas de nom de famille officielle : Dravenholt, Caerwyn, Hearthbane, Valemont, Belladorn, Ravenscroft, Glenhart.</li>"
        "<li>Pas de maison imposée : c'est la Source qui décide.</li>"
        "<li>Une baguette pour seul catalyseur au départ.</li>"
        "</ul></section>"
    )
    return (
        hero("Les règles essentielles", "Créer son personnage", principle, "creation")
        + reminders
        + f'<section class="panel"><h2>Les règles de création</h2><div class="entries grid">{"".join(cards)}</div></section>'
    )


def render_rules():
    out, total, tabs = [], 0, []
    for key, label, path in REGLES:
        soup = md_to_soup(read(path))
        strip_intro(soup)
        count = 0
        for head, body in sections(soup, "h2"):
            if head is None:
                continue
            m = re.match(r"^(\d+) — (.*)$", head.get_text())
            num, name = (m.group(1), m.group(2)) if m else ("", head.get_text())
            count += 1
            out.append(
                f'<article class="rule" data-section="{key}" id="regle-{key}-{num}">'
                f'<div class="rule-head"><span class="rule-num">{num}</span>'
                f'<div><p class="rule-sec">{label}</p><h3>{name}</h3></div></div>'
                f'<div class="rule-body">{html_of(body)}</div></article>'
            )
        total += count
        tabs.append((key, label, count))
    tab_html = "".join(
        f'<button type="button" class="tab" role="tab" data-filter="{k}" aria-selected="{str(i == 0).lower()}">'
        f"{l} <small>{c}</small></button>"
        for i, (k, l, c) in enumerate(tabs)
    )
    return (
        hero(
            "Les bases du jeu",
            "Règlement",
            f"{total} règles en six sections : les bases de jeu et les limites RP à respecter sur Elderwood. "
            "En rejoignant le serveur, tu t'engages à les connaître.",
            "reglement",
        )
        + '<div class="rules-tools"><label class="search" for="rule-search">'
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>'
        '<input id="rule-search" type="search" placeholder="Chercher une règle : metagaming, potions, RPK…" autocomplete="off">'
        "</label>"
        f'<div class="tabs sub-tabs" role="tablist">{tab_html}</div>'
        '<p class="rule-count" aria-live="polite"></p></div>'
        f'<div class="rules">{"".join(out)}</div>'
        '<p class="empty" hidden>Aucune règle ne correspond à cette recherche.</p>'
    ), total


def render_notices():
    """Annonces du staff (conseils/annonces-whitelist.md) → avertissements en tête de l'espace Whitelist."""
    path = ROOT / "conseils/annonces-whitelist.md"
    if not path.exists():
        return ""
    soup = md_to_soup(path.read_text(encoding="utf-8"))
    strip_intro(soup)
    out = []
    for head, body in sections(soup, "h2"):
        if head is None:
            continue
        title, _, meta = head.get_text().partition(" — ")
        frag = BeautifulSoup(html_of(body), "html.parser")
        for el in frag.find_all("p"):
            t = el.get_text(strip=True)
            if t.startswith("@") or slug(t) == slug(title):
                el.decompose()
        meta_html = f'<p class="notice-meta">Annonce du staff · {meta}</p>' if meta else ""
        out.append(
            '<aside class="notice" role="note"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 20h20Z"/><path d="M12 10v4"/><path d="M12 17.5v.01"/></svg>'
            f'<div>{meta_html}<h2>{title}</h2><div class="notice-body">{frag}</div></div></aside>'
        )
    return "".join(out)


# ---------------------------------------------------------------- accueil

HOUSES = [
    ("aerwyn", "Aerwyn", "L'Ephyr", "Bleu", "« J'agis avec droiture et intégrité. »", "Honneur · Protection · Constance", "Althea Aerwyn"),
    ("brumval", "Brumval", "Le Valdorn", "Vert", "« Ma force, c'est de rester fidèle à ceux qui comptent sur moi. »", "Loyauté · Camaraderie · Courage", "Hector Brumval"),
    ("falcon", "Falcon", "L'Aetherion", "Orange", "« La connaissance est une arme redoutable. »", "Savoir · Curiosité · Sagesse", "Eldric Falcon"),
    ("venatrix", "Venatrix", "L'Akkorokamui", "Violet", "« Qui connaît les ficelles contrôle le jeu »", "Ambition · Maîtrise · Influence", "Selena Venatrix"),
]


def render_home(total_rules):
    houses = "".join(
        f'<a class="house h-{k}" href="#ecole"><span class="house-flux">Flux {c}</span>'
        f"<h3>{n}</h3><p class=\"house-beast\">{b}</p><p class=\"house-motto\">{m}</p>"
        f'<p class="house-values">{v}</p><p class="house-founder">Fondée par {f}</p></a>'
        for k, n, b, c, m, v, f in HOUSES
    )
    return f"""
<header class="hero hero-home">
  <div class="hero-art" aria-hidden="true"></div>
  <svg class="hero-owl" aria-hidden="true"><use href="#owl"/></svg>
  <p class="kicker">Serveur roleplay · nanos world</p>
  <h1 class="home-title">Elderwood</h1>
  <p class="hero-lead">Seule grande école de sorcellerie du Royaume-Uni, Elderwood forme les jeunes Résonants à comprendre leur Flux. Dissimulée par un Voile puissant, bâtie autour d'une source de magie unique, elle garde encore aujourd'hui bien des secrets.</p>
  <div class="cta">
    <a class="btn" href="#magie">Découvrir le lore</a>
    <a class="btn btn-ghost" href="#reglement">Lire le règlement</a>
    <a class="btn btn-ghost" href="#whitelist">Préparer sa whitelist</a>
  </div>
</header>

<section class="panel">
  <h2>Les quatre maisons</h2>
  <p class="panel-lead">En 1298, Falcon découvre la Source de Vehr, qui révèle la couleur du Flux de chaque Résonant. Quatre couleurs, quatre fondateurs, quatre maisons. Personne ne choisit la sienne : c'est la Source qui répond.</p>
  <div class="houses">{houses}</div>
</section>

<section class="panel">
  <h2>Par où commencer</h2>
  <div class="paths">
    <a class="path" href="#magie"><span class="path-n">6 chapitres</span><h3>Le lore</h3><p>L'Écho, la Résonance et le Flux, l'école, la société magique, la chronologie, le glossaire et les créatures.</p><span class="path-go">Ouvrir le lore</span></a>
    <a class="path" href="#reglement"><span class="path-n">{total_rules} règles</span><h3>Le règlement</h3><p>Général, vocal, lexique RP, roleplay, zones RPK et familles. Avec une recherche pour retrouver une règle en un instant.</p><span class="path-go">Ouvrir le règlement</span></a>
    <a class="path" href="#whitelist"><span class="path-n">Candidature</span><h3>La whitelist</h3><p>Ce que la douane attend de ton personnage, les redflags à éviter, l'oral et les règles de création.</p><span class="path-go">Ouvrir le guide</span></a>
  </div>
</section>

<section class="panel">
  <h2>2026, l'année de toutes les fractures</h2>
  <ol class="timeline compact">
    <li class="tl-now"><span class="tl-year">2026</span><h4>La tentative de coup d'État</h4><p>L'Ascendance attaque l'AMRU. Le coup échoue, mais le Ministre est assassiné.</p></li>
    <li class="tl-now"><span class="tl-year">2026</span><h4>La mort d'Arthurius Glenwood</h4><p>Le directeur d'Elderwood tombe dans une embuscade de l'Ascendance.</p></li>
    <li class="tl-now"><span class="tl-year">2026</span><h4>La Rupture du Voile</h4><p>Pendant quelques minutes, l'île devient visible depuis le monde Sans-Flux.</p></li>
    <li class="tl-now"><span class="tl-year">2026</span><h4>Tensions entre les Mondes</h4><p>Le secret se resserre et les Dissonants sont de plus en plus nombreux.</p></li>
  </ol>
  <p><a class="btn btn-ghost" href="#contexte">Toute la chronologie</a></p>
</section>
"""


# ---------------------------------------------------------------- assemblage

def build():
    pages = []  # (route, group, html)
    for route, tab, path, kicker, title in LORE:
        pages.append((route, "lore", render_page(route, read(path), kicker, title)))
    rules_html, total = render_rules()
    pages.append(("reglement", "reglement", rules_html))
    for route, tab, path, kicker, title in WL:
        if path:
            pages.append((route, "whitelist", render_page(route, read(path), kicker, title)))
        else:
            pages.append((route, "whitelist", render_creation()))
    notices = render_notices()
    if notices:
        pages = [
            (r, g, h.replace("</header>", "</header>" + notices, 1) if g == "whitelist" else h)
            for r, g, h in pages
        ]
    pages.insert(0, ("accueil", "accueil", render_home(total)))

    lore_tabs = "".join(f'<a class="tab" href="#{r}" data-route="{r}">{t}</a>' for r, t, *_ in LORE)
    wl_tabs = "".join(f'<a class="tab" href="#{r}" data-route="{r}">{t}</a>' for r, t, *_ in WL)
    body = "".join(
        f'<section class="page" id="page-{r}" data-route="{r}" data-group="{g}"{"" if r == "accueil" else " hidden"}>{h}</section>'
        for r, g, h in pages
    )
    tpl = (SITE / "template.html").read_text(encoding="utf-8")
    html = (
        tpl.replace("{{PAGES}}", body)
        .replace("{{LORE_TABS}}", lore_tabs)
        .replace("{{WL_TABS}}", wl_tabs)
    )
    (SITE / "index.html").write_text(html, encoding="utf-8")
    print(f"site/index.html : {len(pages)} pages, {total} règles, {len(html) // 1024} Ko")

    if "--fragment" in sys.argv:
        dest = Path(sys.argv[sys.argv.index("--fragment") + 1])
        frag = re.sub(r"(?s)^.*?<!-- fragment:start -->", "", html)
        frag = re.sub(r"(?s)</body>.*$", "", frag)
        frag = frag.replace("</head>", "").replace("<body>", "")
        dest.write_text(frag, encoding="utf-8")
        print(f"fragment : {dest}")


if __name__ == "__main__":
    build()
