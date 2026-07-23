# Nimbus Sans résumé inputs

The résumé is compiled only with the two font files in this directory. They
come from URW Base35 Fonts release 20200910, distributed by Fedora in
`urw-base35-nimbus-sans-fonts-20200910-27.fc44` and maintained upstream at
[ArtifexSoftware/urw-base35-fonts](https://github.com/ArtifexSoftware/urw-base35-fonts).

`SHA256SUMS` records the exact font and notice bytes. The repository gate
checks those pinned hashes before compilation, invokes Typst 0.14.2 with
`--ignore-system-fonts --ignore-embedded-fonts --font-path resume/fonts`,
compiles twice, byte-compares both results with the tracked PDF, and accepts
only embedded/subsetted Nimbus Sans Regular and Bold according to `pdffonts`.

The font files are licensed under GNU AGPL version 3 with the font embedding
exception in `LICENSE`; `COPYING` contains the accompanying full AGPL text.
Those terms belong to the font authors and are not replaced by the site's
PolyForm or content licenses.
