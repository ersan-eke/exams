# Glossary

**Subject**
A course the user studies. Groups exams and material. Can exist while empty.
_Avoid_: course (in the UI), folder.

**Material**
Everything the user uploads for a Subject that is not an exam: slide decks, scripts, exercises.

**Deck**
One uploaded PDF of Material, with a kind (slides, script or exercises). One deck is one chapter of a Subject.
_Avoid_: document, chapter.

**Outline**
The titles of a Deck in reading order, in two levels: sections (level 1) and the pages under them (level 2).
Built automatically at upload; the user can replace it with an AI-built one and reset it.

**Search**
Finding the pages of a Subject's Material that best answer a question. Needs no LLM and no key.

**Chat**
A saved conversation within one Subject. Holds search turns and AI turns.

**Pinned page**
A page the user selected in a Chat. Only pinned pages are sent to the LLM.

**AI turn**
A Chat message answered by the LLM with the user's own key, from the pinned pages.
