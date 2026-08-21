"""Code-owned constants shared by career-claim release validators.

The number and quantity tokens live here rather than in one validator because
both of them need to recognise a withdrawn claim in ANY rendering, and a
second copy of that machinery is how one validator ends up catching
"1.35 million" while the other lets "1.35M" through (forkwright#168).
"""

FORBIDDEN_PUBLIC_VARIANTS = (
    "largest disbursing office",
    "second-largest",
    "ten-nation",
    "15 European and African nations",
    "60,000-plus personnel",
    "60,000+ service members",
)

SMALL_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
TENS_NUMBER_WORDS = {
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
NUMBER_WORD_VALUES = SMALL_NUMBER_WORDS | TENS_NUMBER_WORDS
NUMBER_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}
NUMBER_WORD_ATOM = (
    r"(?:"
    + "|".join(sorted((*NUMBER_WORD_VALUES, *NUMBER_SCALES), key=len, reverse=True))
    + r")"
)
NUMBER_WORD_SEQUENCE = (
    rf"{NUMBER_WORD_ATOM}(?:(?:\s+|-)(?:and(?:\s+|-))?{NUMBER_WORD_ATOM})*"
)
# WHY the magnitude suffix: "1.35 million" and "1.35M" are the same claim, and
# without it the digit form of an abbreviated quantity does not match at all --
# NUMBER_TOKEN would take "1.35" and then fail its trailing word boundary
# against the "M". A withdrawn figure rewritten as "1.35M" walked past the
# resume gate while it still reported green (forkwright#168).
MAGNITUDE_SUFFIX = r"(?:\s*(?:MM|bn|[KMB])\b)?"
NUMBER_TOKEN = (
    rf"(?:[0-9][0-9,]*(?:\.[0-9]+)?{MAGNITUDE_SUFFIX}|{NUMBER_WORD_SEQUENCE})"
)
QUANTITY_TOKEN = (
    rf"(?:{NUMBER_TOKEN}|(?:a\s+)?(?:couple|dozen|score)|dozens?|scores?|"
    r"few|half(?:\s+(?:a|an))?|many|multiple|several)"
)
