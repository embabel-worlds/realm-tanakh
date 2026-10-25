# realm-tanakh

> **Experimental.** Its types are children of
> [realm-scripture-vocabulary](https://github.com/embabel-worlds/realm-scripture-vocabulary), which must be installed first — a
> child whose parent's realm is missing is refused at load. It also needs a host that writes a child
> type's inherited properties (Embabel hosts from October 2026): a `TanakhVerse` declares little of its own.

The Tanakh — the Hebrew Bible: Torah, Nevi'im and Ketuvim — as a queryable graph: read a verse or a
chapter in Hebrew and English, search in either language, browse the thirty-nine books in Hebrew
order, walk the fifty-four weekly Torah portions, and read any chapter beside the King James however
the two number it. Because a `TanakhVerse` is a `Verse`, a question asked of every scripture is
answered here too, and `MATCH (v:Tanakh:Verse)` asks this one alone.

It grew from realm-torah, which held the five books of Moses; this realm replaces it.

## Shape

```
Mikra ◀─IN─ TanakhBook ◀─IN─ TanakhChapter ◀─IN─ TanakhVerse ─IN_PORTION─▶ Parashah
(HolyBook)  (ScriptureBook)  (ScriptureChapter)  (Verse)                   (ReadingPortion)
                                                     │                       (Torah only)
                                                     └─CORRESPONDS_TO─▶ BibleVerse   (with realm-bible)
```

The holy book is the `Mikra`, the Hebrew word for the scripture as it is read: `Tanakh` is this
realm's provenance label, and a type may not share it.

| | Count | Source |
|---|---|---|
| Mikra | 1 | — |
| TanakhBook | 39 — Torah 5, Nevi'im 21, Ketuvim 13 | Hebrew names from Sefaria's book indexes |
| TanakhChapter | 929 | Sefaria |
| Parashah | 54 | Sefaria's Torah indexes (the `Parasha` structure) |
| TanakhVerse | 23,206 | Hebrew: tanach.us's Leningrad Codex via Sefaria; English: JPS 1917 via Sefaria |

Each book and verse carries its `section` — `torah`, `neviim` or `ketuvim` — so a search can keep to
the Prophets or the Writings.

## Three texts on every verse

| Property | What it is |
|---|---|
| `original` | the Hebrew with vowel points (Tanach with Nikkud) |
| `hebrewPlain` | the same consonantal text without points (Tanach with Text Only) — what a person types to search Hebrew |
| `text` | the JPS 1917 English — the vocabulary's promise: `text` is English, so every scripture can be searched together |

## Hebrew numbering, and the King James

Chapter and verse are the Tanakh's own. Where they differ from the King James's:

- **A psalm's title is a verse.** "A Psalm of David, when he fled from Absalom his son" is Psalms 3:1
  here and unnumbered there, so the King James's 3:1 is 3:2 here. A title may be two verses (Psalm 51),
  or share its verse with the psalm's first line (Psalm 23), when the numberings agree.
- **Chapters break in other places.** Malachi has three chapters, the King James's 4:1–6 being
  3:19–24; Joel has four; the King James's Exodus 22:1 is 21:37 here.
- **One Hebrew verse may be several.** "Thou shalt not murder … bear false witness" is one verse in
  each Decalogue, and four in the King James.

In all, 2,164 of the 23,206 verses number unlike the King James — 270 in the Torah, 383 in the
Prophets, 1,511 in the Writings, 1,055 of them in the Psalms — and 67 are psalm titles with no King
James number. One King James verse, Nehemiah 7:68 ("Their horses … their mules"), is not in the
Leningrad Codex and has no counterpart here.

Nothing is renumbered. Each verse stores `kjvRefs`, the King James verse or verses holding the same
text (none for a psalm's title), and `rules/corresponds.yml` derives `CORRESPONDS_TO` from it to
realm-bible's `BibleVerse` — empty if realm-bible is not installed.

The pairing is not a hand-kept table. `scripts/build_reference.py` ALIGNS each book against
realm-bible's King James text: the best monotone pairing of the two verse sequences, where verses are
compared by the words they share weighted by rarity (so a pair is judged by `Hazeroth`, not by `and
they pitched in`), one-for-one is free, and a split, a join or a verse with no counterpart costs a
little; in the Psalms nothing is split or joined across a psalm, because each is a poem of its own.
On the five books of Moses it reproduces, verse for verse, the hand table realm-torah kept (5,846
verses, 5,852 pairs, no disagreement).

Then the build checks the pairing by tests the aligner did not optimise, and refuses to write if:

- a pairing names a King James verse that does not exist, or leaves one without a counterpart;
- a Hebrew verse is left without one and is not a psalm's title;
- any run of verses paired at one offset reads better shifted one verse either way.

The checks were tested by breaking the pairing and the aligner; each break was refused.

Verse and chapter names are qualified — `Tanakh Genesis 1:1` — because the book names are the
Bible's, and a view that reads every `Verse` looks verses up by `name`. `ref` is the unqualified
`Genesis 1:1`, unique within this realm. Books take the King James's names (`1 Samuel`), except the
`Song of Songs`; its King James references still say `Song of Solomon`.

## Views

| View | Answers |
|---|---|
| `TanakhBooks` | the thirty-nine books in Hebrew order, by section, with Hebrew names and sizes |
| `ReadTanakhVerse` | one verse by its Hebrew-numbered reference, Hebrew and English, with its parashah and King James reference |
| `ReadTanakhChapter` | a whole chapter |
| `FromKingJames` | the Tanakh verse holding a King James verse's text — `Malachi 4:5` finds Malachi 3:23 |
| `NumberingDifferences` | every verse of a book whose Hebrew number is not the King James's |
| `Parashot` | the fifty-four Torah portions with their Hebrew names, bounds and sizes |
| `ReadParashah` | one portion's verses |
| `SearchTanakh` | verses whose English contains a word, in one section or all |
| `SearchHebrew` | verses whose Hebrew contains a word typed without points |
| `TanakhBesideKingJames` | a chapter verse by verse beside its King James counterparts, through `CORRESPONDS_TO` (needs realm-bible) |

Searching across scriptures, by word and by meaning, is in realm-scripture-vocabulary.

`sources.yml` declares the Tanakh as documents too — one per chapter in the JPS English
(`tanakh://jps/Ps.23`), tagged `scripture` so the vocabulary's meaning search ranks it beside every
other scripture — embedded on install.

## Rebuilding the reference data

```
python scripts/build_reference.py
```

Downloads into `data/source/` (ignored by git), aligns and checks the King James pairing against
`../realm-bible/reference/`, and rewrites `reference/`. realm-bible must be checked out beside it:
without the King James text there is nothing to align against, and the build refuses rather than
write an unpaired Tanakh.

## Licences

- **English**: *The Holy Scriptures According to the Masoretic Text: A New Translation*, Jewish
  Publication Society, 1917. Public domain. Text from [Sefaria](https://www.sefaria.org).
- **Hebrew**: the Westminster Leningrad Codex as published by [tanach.us](https://tanach.us) (Tanach
  with Nikkud; Tanach with Text Only). Public domain. Text from Sefaria.
- **Parashah divisions and Hebrew book names**: Sefaria's book indexes.
- **Code**: GPL-3.0, as realm-bible.
