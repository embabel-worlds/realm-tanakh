#!/bin/sh
# Ground truth for realm-tanakh, against Sefaria, the source it was built from, fetched fresh.
#
#   L1  every view answers BY NAME on its defaults, and is not empty
#   L2  the graph against Sefaria: all thirty-nine books' chapter and verse counts (Sefaria's index),
#       and the JPS 1917 English, pointed Hebrew and plain Hebrew of every verse in a fixed set of
#       chapters — the ones where the numberings part among them — exactly, cleaned as the build
#       cleans them; the Torah's verses each in exactly one parashah; the stored reference/ loaded whole
#   L3  views against the graph and the source: King James references found in Hebrew numbering,
#       a chapter, the English and Hebrew searches
#   L4  with realm-bible installed: chapters are paired with exactly the King James verses their stored
#       `kjvRefs` name (skipped, and said so, when realm-bible is absent)
#
# No producers and no source calls at query time — the text is stored — so there is no pushdown or
# cost check to make. Keyless: Sefaria's API is public. About fifty Sefaria calls.
#
#   APPLIANCE=http://127.0.0.1:11043 AUTH=user:pass sh tests/verify.sh
#
# The last line on success is exactly `ALL CHECKS PASS`; any failure exits non-zero.
set -e
AUTHCFG=$(mktemp); trap 'rm -f "$AUTHCFG"' EXIT
if [ -n "${TOKEN:-}" ]; then printf 'header = "Authorization: Bearer %s"\n' "$TOKEN" > "$AUTHCFG"
else printf 'user = "%s"\n' "${AUTH:?set AUTH (user:pass) or TOKEN}" > "$AUTHCFG"; fi
APPLIANCE="${APPLIANCE:-http://127.0.0.1:11043}"
BATTERY_LIB="$(dirname "$0")/lib" APPLIANCE="$APPLIANCE" AUTHCFG="$AUTHCFG" python3 - "$(dirname "$0")/.." <<'PY'
import glob, json, os, re, subprocess, sys, time, urllib.parse, urllib.request, yaml
from html.parser import HTMLParser
base, auth, realm = os.environ["APPLIANCE"], os.environ["AUTHCFG"], sys.argv[1]
ENGLISH, POINTED, PLAIN = "The Holy Scriptures: A New Translation (JPS 1917)", "Tanach with Nikkud", "Tanach with Text Only"
# (Sefaria title, the realm's book name, chapter): where Hebrew and King James numbering part, a
# psalm with a title, the Decalogue, the verse the Leningrad Codex lacks, and two plain chapters.
SAMPLE = [("Genesis", "Genesis", 1), ("Exodus", "Exodus", 20), ("Exodus", "Exodus", 21), ("Leviticus", "Leviticus", 16),
          ("Deuteronomy", "Deuteronomy", 5), ("Psalms", "Psalms", 51), ("Psalms", "Psalms", 23), ("Malachi", "Malachi", 3),
          ("Song of Songs", "Song of Songs", 7), ("Nehemiah", "Nehemiah", 7), ("Joel", "Joel", 3), ("I Samuel", "1 Samuel", 21)]
fail = 0

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "realm-tanakh tests/verify.sh"})
    for attempt in range(4):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
        except OSError:
            if attempt == 3: raise
            time.sleep(2 ** attempt)
def post(path, body):
    out = subprocess.run(["curl", "-s", "--max-time", "600", "-K", auth, "-X", "POST", base + path,
                          "-H", "Content-Type: application/json", "-d", json.dumps(body)],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out, strict=False)
    except ValueError:
        return {"error": "not JSON: " + out[:200]}
# A figure is only this realm's when the engine says the answer is whole. short() is the battery
# library's (tests/lib, pinned from embabel-worlds/realm-spec): None when whole, else the line that
# stands in for the figure, "REFUSED: <why>" or "PARTIAL <figure>: <the engine's reason>".
import os as _os, sys as _sys
_sys.path.insert(0, _os.environ["BATTERY_LIB"])
from short import short  # noqa: E402
def kg(cypher):
    r = post("/api/v1/admin/kg/execute", {"cypher": cypher})
    if r.get("error"):
        raise SystemExit("  FAIL query REFUSED: %s\n    %s" % (str(r["error"])[:200], cypher))
    # A short count stops the battery as a refusal does: every check after it would read the same gap.
    rows = r.get("rows") or []
    s = short(r, rows[0]["n"] if len(rows) == 1 and "n" in rows[0] else "%d rows" % len(rows))
    if s:
        raise SystemExit("  FAIL query %s\n    %s" % (s, cypher))
    return r.get("rows") or []
def view(name, args=None, whole=True):
    r = post("/api/v1/views/%s/invoke" % name, {"args": args or {}})
    # Rows a view marks short are not its answer, so no check counts them. L1 asks with whole=False
    # because it reports each view's verdict itself and goes on to the next.
    s = whole and short(r, len(r.get("data") or []))
    if s:
        raise SystemExit("  FAIL view %s %s: %s" % (name, json.dumps(args or {}), s))
    return r
def check(what, want, got):
    global fail
    if want == got: print("  ok   %s = %s" % (what, got if len(str(got)) < 80 else str(got)[:77] + "..."))
    else: print("  FAIL %s: expected %s, got %s" % (what, str(want)[:300], str(got)[:300])); fail = 1
def records(kind):
    out = []
    for f in sorted(glob.glob(os.path.join(realm, "reference", "*.yml"))):
        out += [r["data"] for r in yaml.safe_load(open(f)) or [] if r.get("type") == kind]
    return out

class Text(HTMLParser):
    """scripts/build_reference.py's clean(), on the standard library: footnotes are commentary and go."""
    VOID = {"br", "img", "hr", "wbr"}
    def __init__(self): super().__init__(); self.out, self.skip, self.stack = [], 0, []
    def handle_starttag(self, tag, attrs):
        if tag in self.VOID: return
        cls = (dict(attrs).get("class") or "").split()
        drop = (tag == "sup" and "footnote-marker" in cls) or (tag == "i" and "footnote" in cls) or self.skip > 0
        self.stack.append(drop); self.skip += drop
    def handle_endtag(self, tag):
        if tag not in self.VOID and self.stack: self.skip -= self.stack.pop()
    def handle_data(self, d):
        if not self.skip: self.out.append(d)
def clean(html):
    p = Text(); p.feed(html); p.close()
    text = re.sub(r"\s*\{[פס]\}\s*", " ", re.sub(r"\s+", " ", "".join(p.out)).strip()).strip()
    return re.sub(r"(?<=s)’(?=[A-Za-z])", "’ ", text)

# The stored reference is written in the background after the realm reports active, so a battery that
# starts at once reads a half-written graph. Wait until every stored verse of this realm, and of
# realm-bible (which it requires), is there: the counts the stored files and the holy book declare.
import time
def wait_seeded(what, query, want):
    deadline = time.time() + 1800
    while True:
        got = kg(query)[0]["n"]
        if got == want: return
        if time.time() > deadline:
            raise SystemExit("  FAIL %s: %d of %d written after 30 minutes" % (what, got, want))
        print("  wait %s: %d of %d written" % (what, got, want)); time.sleep(30)
for label in ['TanakhVerse']:
    wait_seeded(label, "MATCH (v:%s) RETURN count(v) AS n" % label, len(records(label)))
# realm-bible is required, so it is always installed; its canon node may itself still be on its way.
wait_seeded("the Bible's holy book", "MATCH (h:HolyBook {scripture: 'bible'}) RETURN count(h) AS n", 1)
wait_seeded("BibleVerse", "MATCH (b:BibleVerse) RETURN count(b) AS n",
            kg("MATCH (h:HolyBook {scripture: 'bible'}) RETURN h.verseCount AS n")[0]["n"])
bible = True

print("== L1: every view answers by name ==")
for f in sorted(glob.glob(os.path.join(realm, "views", "*.yml"))):
    for v in yaml.safe_load(open(f)):
        r = view(v["name"], whole=False)
        rows = r.get("data") or []
        if r.get("status") != "SUCCEEDED":
            print("  FAIL %s: %s %s" % (v["name"], r.get("status"), str(r.get("error") or r)[:200])); fail = 1
        elif short(r, len(rows)):
            print("  FAIL %s: %s" % (v["name"], short(r, len(rows)))); fail = 1
        elif not rows:
            print("  FAIL %s answered no rows on its defaults" % v["name"]); fail = 1
        else:
            print("  ok   %-22s %d rows" % (v["name"], len(rows)))

print("== L2: the graph against Sefaria ==")
books = kg("MATCH (b:TanakhBook) RETURN b.name AS name, b.osis AS osis, b.chapterCount AS chapters, b.verseCount AS verses ORDER BY b.bookOrder")
check("thirty-nine books", 39, len(books))
counted = {r["b"]: [r["c"], r["v"]] for r in kg(
    "MATCH (b:TanakhBook)<-[:IN]-(c:TanakhChapter)<-[:IN]-(v:TanakhVerse) RETURN b.name AS b, count(DISTINCT c) AS c, count(v) AS v")}
titles = {r["name"]: r for r in books}
SEFARIA = {"1 Samuel": "I Samuel", "2 Samuel": "II Samuel", "1 Kings": "I Kings", "2 Kings": "II Kings",
           "1 Chronicles": "I Chronicles", "2 Chronicles": "II Chronicles"}
want, stored = {}, {}
for name in titles:
    index = get("https://www.sefaria.org/api/v2/raw/index/" + urllib.parse.quote(SEFARIA.get(name, name)))
    want[name] = index["schema"]["lengths"][:2]
    stored[name] = [titles[name]["chapters"], titles[name]["verses"]]
check("chapters and verses per book in the graph = Sefaria's index", want, counted)
check("  ...and = each TanakhBook's stored counts", want, stored)
for title, name, ch in SAMPLE:
    q = "&".join("version=" + urllib.parse.quote(v) for v in ("english|" + ENGLISH, "hebrew|" + POINTED, "hebrew|" + PLAIN))
    data = get("https://www.sefaria.org/api/v3/texts/%s.%d?%s" % (urllib.parse.quote(title), ch, q))
    texts = {v["versionTitle"]: v["text"] for v in data["versions"]}
    src = [{"verse": i + 1, "text": clean(e), "original": clean(p), "hebrewPlain": clean(pl)}
           for i, (e, p, pl) in enumerate(zip(texts[ENGLISH], texts[POINTED], texts[PLAIN]))]
    got = kg("""MATCH (:TanakhBook {name: '%s'})<-[:IN]-(:TanakhChapter {chapter: %d})<-[:IN]-(v:TanakhVerse)
                RETURN v.verse AS verse, v.text AS text, v.original AS original, v.hebrewPlain AS hebrewPlain
                ORDER BY verse""" % (name, ch))
    check("%s %d: %d verses, English, pointed and plain Hebrew, exactly" % (name, ch, len(src)), src, got)
torah = kg("MATCH (v:TanakhVerse {section: 'torah'}) OPTIONAL MATCH (v)-[:IN_PORTION]->(p:Parashah) "
           "WITH v, count(p) AS n RETURN n, count(v) AS verses")
check("every Torah verse in exactly one parashah", [{"n": 1, "verses": sum(want[b][1] for b in
      ("Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy"))}], torah)
check("fifty-four parashot", 54, kg("MATCH (p:Parashah) RETURN count(p) AS n")[0]["n"])
check("the stored reference/ loaded whole (verses)", len(records("TanakhVerse")),
      kg("MATCH (v:TanakhVerse) RETURN count(v) AS n")[0]["n"])

print("== L3: views against the graph and the source ==")
for kjv, tanakh in (("Exodus 22:1", "Tanakh Exodus 21:37"), ("Malachi 4:5", "Tanakh Malachi 3:23"), ("Psalms 51:1", "Tanakh Psalms 51:3")):
    check("FromKingJames %s" % kjv, [tanakh], [r["tanakhReference"] for r in view("FromKingJames", {"ref": kjv}).get("data") or []])
check("ReadTanakhChapter Malachi 3 = Sefaria", 24, len(view("ReadTanakhChapter", {"book": "Malachi", "chapter": 3}).get("data") or []))
n = kg("MATCH (v:TanakhVerse) WHERE toLower(v.text) CONTAINS 'goat' RETURN count(v) AS n")[0]["n"]
check("SearchTanakh 'goat' = Cypher count", n, len(view("SearchTanakh", {"term": "goat", "limit": 10000}).get("data") or []))
n = kg("MATCH (v:TanakhVerse) WHERE v.hebrewPlain CONTAINS 'שעיר' RETURN count(v) AS n")[0]["n"]
check("SearchHebrew 'שעיר' = Cypher count", n, len(view("SearchHebrew", {"term": "שעיר", "limit": 10000}).get("data") or []))
check("  ...and it is there", True, n > 0)

print("== L4: verses paired with the King James ==")
if not bible:
    print("  skip realm-bible is not installed, so CORRESPONDS_TO is empty by design")
else:
    stored = records("TanakhVerse")
    for book, ch in (("Malachi", 3), ("Psalms", 51), ("Exodus", 20)):
        want = sorted((v["verse"], k) for v in stored if v["ref"].startswith("%s %d:" % (book, ch)) for k in v.get("kjvRefs") or [])
        rows = view("TanakhBesideKingJames", {"book": book, "chapter": ch}).get("data") or []
        got = sorted((r["verse"], k) for r in rows for k in r["kingJames"])
        check("%s %d pairs exactly its stored kjvRefs (%d)" % (book, ch, len(want)), want, got)

if fail: print("FAILED"); sys.exit(1)
print("ALL CHECKS PASS")
PY
