"""
Build the realm's reference data from its published sources.

The stored graph is Mikra → TanakhBook → TanakhChapter → TanakhVerse, with each verse of the five
books of Moses also IN_PORTION its Parashah. Every verse carries three texts, all stored because all
must be SEARCHABLE:
  original     the Hebrew with vowel points (Tanach with Nikkud), to read and show;
  hebrewPlain  the same consonantal text without points (Tanach with Text Only) — what a person
               types to search Hebrew;
  text         the JPS 1917 English, the field the scripture vocabulary promises is English, so
               the Tanakh can be searched beside the Bible and the Quran.

Sources, downloaded into data/source/ on first run, all from Sefaria (sefaria.org):
  The Holy Scriptures: A New Translation (JPS 1917) — public domain.
  Tanach with Nikkud, Tanach with Text Only — public domain, from tanach.us's Westminster
      Leningrad Codex.
  The book indexes, for each book's Hebrew name and the fifty-four parashot (Sefaria's `Parasha`
      alternate structure).

Numbering is HEBREW throughout, because it is the Tanakh's own: Exodus 22:1 in the King James is
21:37 here, and a psalm's title is its first verse. `kjvRefs` names the King James verse or verses
that hold the same text, so rules/corresponds.yml can draw CORRESPONDS_TO to realm-bible without
anyone renumbering. The pairing is not a table: it is ALIGNED, book by book, against realm-bible's
own King James text (see align()), and then checked by tests the aligner does not use. Without
realm-bible beside this realm the build cannot pair, and refuses rather than guess.

Run from the realm root:  python scripts/build_reference.py
"""

import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "source"
REFERENCE = ROOT / "reference"
BIBLE = ROOT.parent / "realm-bible" / "reference"

ENGLISH = "The Holy Scriptures: A New Translation (JPS 1917)"
POINTED = "Tanach with Nikkud"
PLAIN = "Tanach with Text Only"

TORAH, NEVIIM, KETUVIM = "torah", "neviim", "ketuvim"

# In Hebrew canonical order: (Sefaria title, OSIS, name, section, transliterated Hebrew name). The
# name is the King James's, so `Genesis 1:1` means one thing in every scripture installed — except
# the Song of Songs, which is its name in the Tanakh; its kjvRefs still say `Song of Solomon`.
BOOKS = [
    ("Genesis", "Gen", "Genesis", TORAH, "Bereshit"),
    ("Exodus", "Exod", "Exodus", TORAH, "Shemot"),
    ("Leviticus", "Lev", "Leviticus", TORAH, "Vayikra"),
    ("Numbers", "Num", "Numbers", TORAH, "Bamidbar"),
    ("Deuteronomy", "Deut", "Deuteronomy", TORAH, "Devarim"),
    ("Joshua", "Josh", "Joshua", NEVIIM, "Yehoshua"),
    ("Judges", "Judg", "Judges", NEVIIM, "Shoftim"),
    ("I Samuel", "1Sam", "1 Samuel", NEVIIM, "Shmuel Alef"),
    ("II Samuel", "2Sam", "2 Samuel", NEVIIM, "Shmuel Bet"),
    ("I Kings", "1Kgs", "1 Kings", NEVIIM, "Melachim Alef"),
    ("II Kings", "2Kgs", "2 Kings", NEVIIM, "Melachim Bet"),
    ("Isaiah", "Isa", "Isaiah", NEVIIM, "Yeshayahu"),
    ("Jeremiah", "Jer", "Jeremiah", NEVIIM, "Yirmeyahu"),
    ("Ezekiel", "Ezek", "Ezekiel", NEVIIM, "Yechezkel"),
    ("Hosea", "Hos", "Hosea", NEVIIM, "Hoshea"),
    ("Joel", "Joel", "Joel", NEVIIM, "Yoel"),
    ("Amos", "Amos", "Amos", NEVIIM, "Amos"),
    ("Obadiah", "Obad", "Obadiah", NEVIIM, "Ovadyah"),
    ("Jonah", "Jonah", "Jonah", NEVIIM, "Yonah"),
    ("Micah", "Mic", "Micah", NEVIIM, "Michah"),
    ("Nahum", "Nah", "Nahum", NEVIIM, "Nachum"),
    ("Habakkuk", "Hab", "Habakkuk", NEVIIM, "Chavakuk"),
    ("Zephaniah", "Zeph", "Zephaniah", NEVIIM, "Tzefanyah"),
    ("Haggai", "Hag", "Haggai", NEVIIM, "Chaggai"),
    ("Zechariah", "Zech", "Zechariah", NEVIIM, "Zecharyah"),
    ("Malachi", "Mal", "Malachi", NEVIIM, "Malachi"),
    ("Psalms", "Ps", "Psalms", KETUVIM, "Tehillim"),
    ("Proverbs", "Prov", "Proverbs", KETUVIM, "Mishlei"),
    ("Job", "Job", "Job", KETUVIM, "Iyov"),
    ("Song of Songs", "Song", "Song of Songs", KETUVIM, "Shir HaShirim"),
    ("Ruth", "Ruth", "Ruth", KETUVIM, "Rut"),
    ("Lamentations", "Lam", "Lamentations", KETUVIM, "Eichah"),
    ("Ecclesiastes", "Eccl", "Ecclesiastes", KETUVIM, "Kohelet"),
    ("Esther", "Esth", "Esther", KETUVIM, "Esther"),
    ("Daniel", "Dan", "Daniel", KETUVIM, "Daniel"),
    ("Ezra", "Ezra", "Ezra", KETUVIM, "Ezra"),
    ("Nehemiah", "Neh", "Nehemiah", KETUVIM, "Nechemyah"),
    ("I Chronicles", "1Chr", "1 Chronicles", KETUVIM, "Divrei HaYamim Alef"),
    ("II Chronicles", "2Chr", "2 Chronicles", KETUVIM, "Divrei HaYamim Bet"),
]

# The aligner's moves, (Hebrew verses, King James verses) → cost. One for one is free. A split — one
# Hebrew verse that the King James counts as several, as each Decalogue's "Thou shalt not murder …
# bear false witness" is four — and a join cost a little, so the aligner reaches for them only when
# the words demand it. A verse with no counterpart costs more: a psalm's title is a Hebrew verse the
# King James prints unnumbered, and a few verses are in one text and not the other.
MOVES = {(1, 1): 0.0, (1, 2): 0.15, (1, 3): 0.15, (1, 4): 0.15, (2, 1): 0.15, (1, 0): 0.2, (0, 1): 0.2}

# Verses the aligner may leave without a counterpart, and why. Anything else it leaves unpaired is a
# refusal: an aligner that can drop a verse anywhere could hide a misreading in a drop.
#   Psalms   — a Hebrew title verse (the King James prints the title above verse 1, unnumbered).
#   KING JAMES verses the Leningrad Codex does not have, listed by name below. An entry the
#   alignment does not need is refused too, so the list cannot outlive what it explains.
UNPAIRED_KJV = {
    "Nehemiah 7:68": "the Leningrad Codex does not have it (“Their horses … their mules”); the King James "
                     "has it from other Hebrew manuscripts, as Ezra 2:66 does",
}

# How the alignment is checked, by a test it did not optimise. A misaligned run is a SHIFT — a run of
# verses each paired with the King James verse one out — so over every run of constant offset, the
# English of the pairs must read more alike than the same pairs moved a verse either way. A single
# verse cannot be the test, because Numbers 33's camps are listed "from X, and pitched in Y", each
# verse naming its neighbour's place, and JPS and the King James spell them differently.
SHIFTED = (-1, 1)


def get(url: str, path: Path):
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "realm-tanakh build_reference"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    path.write_bytes(response.read())
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        time.sleep(0.2)
    return json.loads(path.read_text(encoding="utf-8"))


def chapter_texts(book: str, chapter: int) -> dict[str, list[str]]:
    query = "&".join(f"version={urllib.parse.quote(lang + '|' + title)}"
                     for lang, title in [("english", ENGLISH), ("hebrew", POINTED), ("hebrew", PLAIN)])
    data = get(f"https://www.sefaria.org/api/v3/texts/{urllib.parse.quote(book)}.{chapter}?{query}",
               SOURCE / f"{book}.{chapter}.json")
    texts = {v["versionTitle"]: v["text"] for v in data["versions"]}
    if set(texts) != {ENGLISH, POINTED, PLAIN} or len({len(t) for t in texts.values()}) != 1:
        sys.exit(f"{book} {chapter}: the three versions are missing or number differently")
    return texts


def clean(html: str) -> str:
    """Sefaria's text may carry markup; footnotes are commentary, not scripture, so they go."""
    soup = BeautifulSoup(html, "html.parser")
    for note in soup.select("sup.footnote-marker, i.footnote"):
        note.decompose()
    text = re.sub(r"\s+", " ", soup.get_text()).strip()
    text = re.sub(r"\s*\{[פס]\}\s*", " ", text).strip()
    # Sefaria's JPS 1917 drops the space after every plural possessive — "fathers’houses",
    # "goats’hair", "Moses’father"; a singular possessive ("father’s") is untouched. Restored,
    # because a search for "goats' hair" must find it.
    return re.sub(r"(?<=s)’(?=[A-Za-z])", "’ ", text)


def words(text: str) -> set[str]:
    """Hyphens go first: JPS writes `Kibroth-hattaavah` where the King James writes `Kibrothhattaavah`."""
    return set(re.findall(r"[a-z]+", text.lower().replace("-", "")))


RARITY: dict[str, float] = {}


def learn_rarity(kjv: list[tuple[str, str]]) -> None:
    """Inverse document frequency over the King James verses being compared against."""
    RARITY.clear()
    count: dict[str, int] = {}
    for _, text in kjv:
        for w in words(text):
            count[w] = count.get(w, 0) + 1
    for w, c in count.items():
        RARITY[w] = math.log(len(kjv) / c)


def weight(ws: set[str]) -> float:
    return sum(RARITY.get(w, 1.0) for w in ws)


def likeness_sets(a: set[str], b: set[str]) -> float:
    """Shared words weighted by rarity, so `Hazeroth` decides a pair and `and pitched in` does not."""
    return weight(a & b) / max(1e-9, weight(a | b))


def likeness(a: str, b: str) -> float:
    return likeness_sets(words(a), words(b))


def align(hebrew: list[str], kjv: list[str], hebrew_chapters: list[int],
          kjv_chapters: list[int], whole_chapters: bool) -> list[tuple[list[int], list[int]]]:
    """
    The best monotone pairing of a book's Hebrew-numbered verses with its King James verses: a
    sequence of MOVES whose summed likeness, less their costs, is greatest. Book by book rather than
    chapter by chapter, because chapters are where the numberings part (Malachi 3:19 is the King
    James's 4:1). Searched in a band about the diagonal: the two never drift further apart than the
    difference in their lengths plus the titles and splits between, and a full table over Psalms
    would be millions of cells for nothing.

    With `whole_chapters`, a split or a join stays inside one chapter on each side. That is the
    Psalms: each psalm is a poem of its own, and without the rule a psalm's title joins the last line
    of the psalm before whenever the two translations word that line apart. Elsewhere a chapter is a
    later division of a continuous text and a sentence may run across it: Hebrew 1 Samuel 21:1 is the
    second half of the King James's 20:42, and Hebrew Isaiah 63:19 holds the King James's 64:1.
    """
    hw = [words(t) for t in hebrew]
    kw = [words(t) for t in kjv]
    n, m = len(hebrew), len(kjv)
    band = abs(n - m) + 60
    best: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {(0, 0): (0.0, None)}
    for i in range(n + 1):
        centre = round(i * m / n) if n else 0
        for j in range(max(0, centre - band), min(m, centre + band) + 1):
            here = best.get((i, j))
            if here is None:
                continue
            for (a, b), cost in MOVES.items():
                ni, nj = i + a, j + b
                if ni > n or nj > m:
                    continue
                if whole_chapters and (len(set(hebrew_chapters[i:ni])) > 1 or len(set(kjv_chapters[j:nj])) > 1):
                    continue
                if a and b:
                    gain = likeness_sets(set().union(*hw[i:ni]), set().union(*kw[j:nj]))
                else:
                    gain = 0.0
                score = here[0] + gain - cost
                if score > best.get((ni, nj), (-math.inf, None))[0]:
                    best[(ni, nj)] = (score, (i, j))
    if (n, m) not in best:
        sys.exit("the alignment band was too narrow to reach the end of the book")
    steps, at = [], (n, m)
    while at != (0, 0):
        prev = best[at][1]
        steps.append((list(range(prev[0], at[0])), list(range(prev[1], at[1]))))
        at = prev
    return steps[::-1]


def shifted(ref: str, by: int) -> str:
    head, verse = ref.rsplit(":", 1)
    return f"{head}:{int(verse) + by}"


def misaligned(pairs: list[tuple[str, str]], kjv: dict[str, str]) -> int | None:
    """The shift that reads better than the alignment's own pairing, if any."""
    def score(by: int) -> float:
        return sum(likeness(text, kjv.get(shifted(ref, by), "")) for text, ref in pairs)
    own = score(0)
    return next((by for by in SHIFTED if score(by) >= own), None)


def kjv_verses(osis: str) -> list[tuple[str, str]]:
    """realm-bible's King James verses of one book, in order, as (name, text)."""
    path = next(BIBLE.glob(f"bible-03-verses-*-{osis}.yml"), None)
    if path is None:
        sys.exit(f"realm-bible's King James text for {osis} is not beside this realm ({BIBLE}); "
                 f"the pairing cannot be aligned or checked without it")
    rows = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows.sort(key=lambda r: r["data"]["ordinal"])
    return [(r["data"]["name"], r["data"]["text"]) for r in rows]


def osis_of(kjv_name: str, osis: str) -> str:
    chapter, verse = kjv_name.rsplit(" ", 1)[1].split(":")
    return f"{osis}.{chapter}.{verse}"


def check(book: str, kjv_book: str, verses: list[dict], kjv: list[tuple[str, str]]) -> list[str]:
    """
    The refusals, independent of how the pairing was found: every King James ref exists, every King
    James verse is paired unless UNPAIRED_KJV says why not, a Hebrew verse goes unpaired only as a
    psalm's title, and no run of constant offset reads better moved a verse either way.
    """
    text_of = dict(kjv)
    problems, covered = [], set()
    runs: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for v in verses:
        refs = v["kjvRefs"]
        for ref in refs:
            if ref not in text_of:
                problems.append(f"{v['ref']} maps to {ref}, which the King James does not have")
            covered.add(ref)
        if not refs and not (book == "Psalms" and v["verse"] <= 2):
            problems.append(f"{v['ref']} has no King James counterpart, and is not a psalm's title")
        if len(refs) == 1 and refs[0] in text_of:
            kch, kv = map(int, refs[0].rsplit(" ", 1)[1].split(":"))
            runs.setdefault((kch, kv - v["verse"]), []).append((v["text"], refs[0]))
    for name, _ in kjv:
        if name not in covered and name not in UNPAIRED_KJV:
            problems.append(f"King James {name} has no {book} counterpart")
        if name in covered and name in UNPAIRED_KJV:
            problems.append(f"King James {name} is listed as having no counterpart, but has one")
    for (kch, offset), run in runs.items():
        by = misaligned(run, text_of)
        if by is not None:
            problems.append(f"{book}: the {len(run)} verses paired with {kjv_book} {kch} at offset "
                            f"{offset:+d} read better moved {by:+d}")
    return problems


def parashot() -> list[dict]:
    out = []
    for title, _, name, section, _ in BOOKS:
        if section != TORAH:
            continue
        index = get(f"https://www.sefaria.org/api/v2/raw/index/{title}", SOURCE / f"index-{title}.json")
        for node in index["alt_structs"]["Parasha"]["nodes"]:
            m = re.fullmatch(rf"{title} (\d+):(\d+)-(?:(\d+):)?(\d+)", node["wholeRef"])
            if not m:
                sys.exit(f"parashah {node['sharedTitle']}: unexpected range {node['wholeRef']}")
            # Within one chapter Sefaria writes `31:1-30`, leaving the end's chapter implicit.
            m = [None, m[1], m[2], m[3] or m[1], m[4]]
            term = get(f"https://www.sefaria.org/api/terms/{urllib.parse.quote(node['sharedTitle'])}",
                       SOURCE / f"term-{slug(node['sharedTitle'])}.json")
            hebrew = next(t["text"] for t in term["titles"] if t["lang"] == "he" and t.get("primary"))
            out.append({"name": node["sharedTitle"], "hebrewName": hebrew, "book": name,
                        "start": (int(m[1]), int(m[2])), "end": (int(m[3]), int(m[4]))})
    if len(out) != 54:
        sys.exit(f"{len(out)} parashot, not 54")
    return out


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def header(lines: str) -> str:
    return "\n".join(f"# {line}" if line else "#" for line in lines.strip().splitlines()) + "\n\n"


def write(name: str, comment: str, records: list[dict]) -> None:
    body = yaml.dump(records, allow_unicode=True, sort_keys=False, width=100_000)
    (REFERENCE / name).write_text(header(comment) + body, encoding="utf-8")


def build_book(title: str, osis: str, name: str, section: str, ordinal: int,
               portion_of) -> tuple[list[dict], list[dict], int, list[str]]:
    """One book's chapters and verses, paired with the King James; the problems check() found."""
    index = get(f"https://www.sefaria.org/api/v2/raw/index/{urllib.parse.quote(title)}",
                SOURCE / f"index-{title}.json")
    chapters, verses = [], []
    for chapter in range(1, index["schema"]["lengths"][0] + 1):
        texts = chapter_texts(title, chapter)
        chapters.append({
            "type": "TanakhChapter",
            "data": {"osis": f"{osis}.{chapter}", "scripture": "tanakh", "name": f"Tanakh {name} {chapter}",
                     "book": osis, "section": section, "chapter": chapter, "verseCount": len(texts[ENGLISH]),
                     "documentUri": f"tanakh://jps/{osis}.{chapter}"},
            "relations": [{"predicate": "IN", "to": {"type": "TanakhBook", "osis": osis}}],
        })
        for n, (english, pointed, plain) in enumerate(zip(texts[ENGLISH], texts[POINTED], texts[PLAIN]), start=1):
            ordinal += 1
            data = {
                "osis": f"{osis}.{chapter}.{n}", "scripture": "tanakh", "name": f"Tanakh {name} {chapter}:{n}",
                "ref": f"{name} {chapter}:{n}", "book": osis, "section": section, "chapter": chapter,
                "verse": n, "ordinal": ordinal, "text": clean(english), "translation": "JPS 1917",
                "original": clean(pointed), "hebrewPlain": clean(plain),
            }
            relations = [{"predicate": "IN", "to": {"type": "TanakhChapter", "osis": f"{osis}.{chapter}"}}]
            if section == TORAH:
                p = portion_of(name, chapter, n)
                data["parashah"] = p["name"]
                relations.append({"predicate": "IN_PORTION", "to": {"type": "Parashah", "key": p["key"]}})
            verses.append({"type": "TanakhVerse", "data": data, "relations": relations})

    kjv = kjv_verses(osis)
    learn_rarity(kjv)
    data = [v["data"] for v in verses]
    kjv_chapters = [int(name.rsplit(" ", 1)[1].split(":")[0]) for name, _ in kjv]
    for hs, ks in align([d["text"] for d in data], [t for _, t in kjv],
                        [d["chapter"] for d in data], kjv_chapters, whole_chapters=name == "Psalms"):
        for h in hs:
            data[h]["kjvRefs"] = [kjv[k][0] for k in ks]
    for d in data:
        d["kjvOsis"] = [osis_of(ref, osis) for ref in d["kjvRefs"]]
    kjv_book = kjv[0][0].rsplit(" ", 1)[0]
    return chapters, verses, ordinal, check(name, kjv_book, data, kjv)


def main() -> None:
    SOURCE.mkdir(parents=True, exist_ok=True)
    portions = parashot()
    for p in portions:
        p["key"] = slug(p["name"])

    def portion_of(book: str, chapter: int, verse: int) -> dict:
        for p in portions:
            if p["book"] == book and p["start"] <= (chapter, verse) <= p["end"]:
                return p
        sys.exit(f"{book} {chapter}:{verse} is in no parashah")

    books, chapters, verse_files, problems = [], [], [], []
    ordinal = 0
    for order, (title, osis, name, section, transliterated) in enumerate(BOOKS, start=1):
        index = get(f"https://www.sefaria.org/api/v2/raw/index/{urllib.parse.quote(title)}",
                    SOURCE / f"index-{title}.json")
        hebrew = next(t["text"] for t in index["schema"]["titles"] if t["lang"] == "he" and t.get("primary"))
        book_chapters, verses, ordinal, found = build_book(title, osis, name, section, ordinal, portion_of)
        problems += found
        chapters += book_chapters
        books.append({
            "type": "TanakhBook",
            "data": {"osis": osis, "scripture": "tanakh", "name": name, "section": section, "bookOrder": order,
                     "hebrewName": hebrew, "transliteratedName": transliterated,
                     "chapterCount": len(book_chapters), "verseCount": len(verses)},
            "relations": [{"predicate": "IN", "to": {"type": "Mikra", "scripture": "tanakh"}}],
        })
        verse_files.append((order, osis, name, verses))
        differing = sum(1 for v in verses if v["data"]["kjvRefs"] != [v["data"]["ref"]])
        print(f"{name}: {len(book_chapters)} chapters, {len(verses)} verses, {differing} numbered unlike the King James",
              flush=True)

    if problems:
        sys.exit("the King James pairing is refused:\n  " + "\n  ".join(problems))

    REFERENCE.mkdir(exist_ok=True)
    for old in list(REFERENCE.glob("tanakh-*.yml")) + list(REFERENCE.glob("torah-*.yml")):
        old.unlink()
    write("tanakh-01-tanakh.yml", """
The Tanakh as one holy book. Generated by scripts/build_reference.py — do not edit by hand.
""", [{"type": "Mikra", "data": {
        "scripture": "tanakh", "name": "The Tanakh (JPS 1917)", "tradition": "Judaism",
        "originalLanguage": "Hebrew", "translation": "JPS 1917", "chapterCount": len(chapters),
        "verseCount": ordinal,
        "textSource": "Sefaria (sefaria.org): JPS 1917, and Tanach with Nikkud / Text Only from tanach.us",
    }}])
    write("tanakh-02-books.yml", """
The thirty-nine books in Hebrew order — Torah, Nevi'im, Ketuvim — with their Hebrew names.
Generated by scripts/build_reference.py — do not edit by hand.
""", books)
    write("tanakh-03-chapters.yml", """
Every chapter, in Hebrew numbering. Generated by scripts/build_reference.py — do not edit by hand.
""", chapters)
    write("tanakh-04-parashot.yml", """
The fifty-four weekly portions of the Torah, from Sefaria's book indexes, each with the verse it
begins and ends at. Generated by scripts/build_reference.py — do not edit by hand.
""", [{"type": "Parashah", "data": {
        "key": p["key"], "scripture": "tanakh", "name": p["name"], "hebrewName": p["hebrewName"],
        "number": n, "cycle": "fifty-four portions, one read each Sabbath through the year",
        "startsAt": f"Tanakh {p['book']} {p['start'][0]}:{p['start'][1]}",
        "endsAt": f"Tanakh {p['book']} {p['end'][0]}:{p['end'][1]}",
    }} for n, p in enumerate(portions, start=1)])
    for order, osis, name, verses in verse_files:
        write(f"tanakh-05-verses-{order:02d}-{osis}.yml", f"""
Every verse of {name}, in Hebrew numbering: the JPS 1917 English as `text`, the pointed Hebrew as
`original` and the unpointed as `hebrewPlain`, all public domain, from Sefaria. `kjvRefs` names the
King James verse or verses with the same text. Generated by scripts/build_reference.py — do not edit
by hand.
""", verses)

    pairs = sum(len(v["data"]["kjvRefs"]) for *_, vs in verse_files for v in vs)
    print(f"{len(books)} books, {len(chapters)} chapters, 54 parashot, {ordinal} verses written to {REFERENCE}")
    print(f"{pairs} King James pairs, aligned and checked")


if __name__ == "__main__":
    main()
