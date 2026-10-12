"""Rezepte aus Webseiten lesen, auch ohne KI.

Reihenfolge: strukturierte Daten (schema.org/Recipe als JSON-LD), dann Microdata
(``itemprop="recipeIngredient"`` …), zuletzt der Seitentext mit den Überschriften
„Zutaten“ und „Zubereitung“. Bilder werden nie übernommen.

Außerdem: Links zu einzelnen Rezepten auf einer Übersichtsseite finden.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

from .recipes import clean_recipe, parse_jsonld
from .textparse import parse_text
from .units import UnitOptions

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
NOISE = {"script", "style", "noscript", "svg", "template", "iframe", "select"}
SKIP = NOISE | {"nav", "footer", "aside", "form", "button"}  # beim Seitentext zusätzlich weglassen
BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "table", "tr", "td", "th", "dt", "dd", "dl",
         "h1", "h2", "h3", "h4", "h5", "h6", "br", "figure", "figcaption", "blockquote", "span"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: "Node | None"):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def text(self) -> str:
        parts: list[str] = []

        def walk(n: Node) -> None:
            for c in n.children:
                if isinstance(c, str):
                    parts.append(c)
                elif c.tag not in NOISE:
                    if c.tag in BLOCK and c.tag != "span":
                        parts.append(" ")
                    walk(c)
        walk(self)
        return re.sub(r"\s+", " ", "".join(parts)).strip()


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: v or "" for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(page: str) -> Node:
    b = _Builder()
    try:
        b.feed(page)
        b.close()
    except Exception:  # noqa: BLE001 – kaputtes HTML: nehmen, was bis dahin gelesen wurde
        pass
    return b.root


def _prop(node: Node) -> set[str]:
    return set((node.attrs.get("itemprop") or "").split())


def _meta(root: Node, name: str) -> str:
    for n in root.iter():
        if n.tag == "meta" and name in (n.attrs.get("property"), n.attrs.get("name")):
            return html.unescape(n.attrs.get("content", "")).strip()
    return ""


def parse_microdata(root: Node) -> dict | None:
    scope = next((n for n in root.iter() if "schema.org/Recipe" in (n.attrs.get("itemtype") or "")), None)
    if scope is None:
        return None
    data: dict = {"ingredients": [], "steps": []}
    for n in scope.iter():
        props = _prop(n)
        if not props:
            continue
        value = n.attrs.get("content") or n.text()
        if "name" in props and "title" not in data:
            data["title"] = value
        elif "description" in props and "description" not in data:
            data["description"] = value
        elif props & {"recipeIngredient", "ingredients"}:
            data["ingredients"].append(value)
        elif "recipeInstructions" in props:
            items = [li.text() for li in n.iter() if li.tag == "li"]
            data["steps"].extend(items or re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])", value))
        elif "recipeYield" in props and "serves" not in data:
            data["serves"] = value
    if not data["ingredients"]:
        return None
    return clean_recipe(data)


END = re.compile(r"(ähnliche|weitere|passende|beliebte|neueste) rezepte|kommentar|das könnte|auch interessant|newsletter|"
                 r"teilen|bewertung|related|you may also|comments|more recipes", re.I)


def _markdown(root: Node) -> str:
    """Seitentext mit Markdown-Überschriften und Aufzählungen – Eingabe für ``parse_text``."""
    body = next((n for n in root.iter() if n.tag in ("main", "article")), None) or root
    out: list[str] = []

    def walk(n: Node) -> None:
        for c in n.children:
            if isinstance(c, str):
                if c.strip():
                    out.append(c)
                continue
            if c.tag in SKIP:
                continue
            if c.tag in ("h1", "h2", "h3", "h4"):
                out.append("\n" + "#" * min(int(c.tag[1]), 3) + " " + c.text() + "\n")
            elif c.tag == "li":
                out.append("\n- " + c.text() + "\n")
            elif c.tag in ("tr",):
                out.append("\n- " + " ".join(x.text() for x in c.children if isinstance(x, Node)) + "\n")
            else:
                if c.tag in BLOCK and c.tag != "span":
                    out.append("\n")
                walk(c)
                if c.tag in BLOCK and c.tag != "span":
                    out.append("\n")
    walk(body)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in "".join(out).splitlines()]
    text = []
    for ln in lines:
        if ln.startswith("#") and END.search(ln) and text:
            break
        if ln:
            text.append(ln)
    return "\n".join(text)


def parse_page_text(root: Node, opts: UnitOptions | None = None) -> dict | None:
    text = _markdown(root)
    if not re.search(r"^#+ .*(zutaten|ingredients)", text, re.I | re.M):
        return None
    if not text.lstrip().startswith("# "):
        title = _meta(root, "og:title") or next((n.text() for n in root.iter() if n.tag == "title"), "")
        text = f"# {title}\n" + text
    recipe = parse_text(text, opts or UnitOptions(origin="de"))
    if not recipe["ingredients"] or not recipe["steps"]:
        return None
    recipe.pop("source", None)
    return recipe


def extract_recipe(page: str) -> dict | None:
    """Rezept ohne KI aus einer Seite lesen; None, wenn nichts Brauchbares gefunden wurde."""
    recipe = parse_jsonld(page)
    if recipe and recipe["ingredients"]:
        return recipe
    root = parse_html(page)
    return parse_microdata(root) or parse_page_text(root)


# ---------- Übersichtsseiten ----------

RECIPE_HINT = re.compile(r"rezept|recipe|gericht|kochen", re.I)
NO_RECIPE = re.compile(r"\.(jpe?g|png|gif|webp|svg|pdf|zip|css|js)$|/(tag|tags|kategorie|category|autor|author|login|"
                       r"suche|search|feed|wp-json|page/\d+)(/|$)|print|drucken|share|teilen|mailto:|javascript:", re.I)
DETAIL_QUERY = re.compile(r"\[(recipe|rezept|uid|id)\]=|\b(recipe|rezept|recipe_id|id|uid)=|action\]=show", re.I)
FILTER_QUERY = re.compile(r"(search|suche|filter|cat|kategorie|sort|order|page|seite|tag|ingredients|searchtext)\]?=", re.I)
NEXT = re.compile(r"^(weiter|nächste|vor|next|older|›|»|>)", re.I)


def _in_layout(node: Node) -> bool:
    n = node.parent
    while n is not None:
        if n.tag in ("nav", "header", "footer"):
            return True
        n = n.parent
    return False


def find_links(page: str, base_url: str) -> dict:
    """Links zu einzelnen Rezepten auf einer Übersichtsseite und, falls vorhanden, die nächste Seite."""
    root = parse_html(page)
    base = urlparse(base_url)
    seen: dict[str, str] = {}
    next_url = ""
    for a in root.iter():
        if a.tag != "a" or not a.attrs.get("href"):
            continue
        href = a.attrs["href"].strip()
        url = urljoin(base_url, href).split("#")[0]
        p = urlparse(url)
        if p.scheme not in ("http", "https") or p.netloc != base.netloc:
            continue
        label = a.text() or a.attrs.get("title", "") or a.attrs.get("aria-label", "")
        rel = (a.attrs.get("rel") or "").lower()
        if not next_url and ("next" in rel or (NEXT.match(label) and len(label) < 20)) and url != base_url:
            next_url = url
            continue
        if _in_layout(a):  # Menü, Kopf- und Fußzeile (Blätter-Links stehen oft in <nav>, deshalb erst hier)
            continue
        if url.rstrip("/") == base_url.rstrip("/") or NO_RECIPE.search(url):
            continue
        query = unquote(p.query)
        if not DETAIL_QUERY.search(query) and (p.path == base.path or FILTER_QUERY.search(query)):
            continue  # Filter oder Sortierung derselben Liste
        deeper = p.path.startswith(base.path.rstrip("/") + "/") and p.path.rstrip("/") != base.path.rstrip("/")
        if not (RECIPE_HINT.search(p.path + "?" + p.query) or deeper):
            continue
        if len(label) < 3:
            label = seen.get(url) or ""
        if url not in seen or len(label) > len(seen[url]):
            seen[url] = label[:120]
    # Listen- und Kategorieseiten aussortieren: Seiten, unter denen weitere Treffer liegen,
    # oder deren Detailseiten unter demselben Pfad mit Parameter erreichbar sind
    def is_list(u: str) -> bool:
        p = urlparse(u)
        if DETAIL_QUERY.search(unquote(p.query)):
            return False
        for other in seen:
            if other == u:
                continue
            o = urlparse(other)
            if o.path.startswith(p.path.rstrip("/") + "/") or (o.path == p.path and DETAIL_QUERY.search(unquote(o.query))):
                return True
        return False
    seen = {u: t for u, t in seen.items() if not is_list(u)}
    links = [{"url": u, "title": t or urlparse(u).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")}
             for u, t in seen.items()]
    return {"links": links[:300], "next": next_url}
