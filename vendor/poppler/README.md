# Poppler Windows runtime

The Windows x64 beginner release includes the **unmodified**
`Release-26.09.0-0.zip` from [oschwartz10612/poppler-windows](https://github.com/oschwartz10612/poppler-windows/releases/tag/v26.09.0-0),
renamed to `windows-x64.zip`. The archive is not tracked in this source repository.
`setup.cmd` verifies its SHA256, extracts it to `runtime/`, and checks both tools.
Source checkouts download the same archive when explicitly running setup.

Poppler is Copyright 2005–2026 The Poppler Developers and
Copyright 1996–2011, 2022 Glyph & Cog, LLC (see source files for complete notices).
It is licensed **GPL-2.0-or-later**, not under this project's MIT license.
The complete license is in [COPYING.poppler](COPYING.poppler).
The original archive's embedded poppler-data copyright/license files are retained.
Bundled DLLs retain their own licenses (including LGPL and permissive licenses).

## Corresponding source and build information

- [Poppler 26.09.0 complete source](https://poppler.freedesktop.org/poppler-26.09.0.tar.xz),
  SHA256 `8059eadb6805340768f138c465b57f8164c92b4a0773c37ef031ea6c0d987b2e`.
  A copy is also attached to this project's beginner Release as `poppler-26.09.0.tar.xz`.
- [Conda-forge 26.09.0 build recipe, patches and Windows build scripts](https://github.com/conda-forge/poppler-feedstock/tree/13d784d77510e73d6066a75a79cd8e6040a6a261).
  A source snapshot is attached as `poppler-build-recipes.zip`.
- [Windows packaging scripts at the upstream release commit](https://github.com/oschwartz10612/poppler-windows/tree/dc4cae5410474e4d75c5c494eb1a8c6774e47457).
  This upstream bundles conda-forge binaries; it does not build Poppler itself.
- [poppler-data 0.4.12 source/data](https://poppler.freedesktop.org/poppler-data-0.4.12.tar.gz).

Dependency source, licenses and build recipes are maintained by conda-forge:
[glib](https://github.com/conda-forge/glib-feedstock),
[cairo](https://github.com/conda-forge/cairo-feedstock),
[freetype](https://github.com/conda-forge/freetype-feedstock),
[fontconfig](https://github.com/conda-forge/fontconfig-feedstock),
[harfbuzz](https://github.com/conda-forge/harfbuzz-feedstock),
[libiconv](https://github.com/conda-forge/libiconv-feedstock),
[gettext](https://github.com/conda-forge/gettext-feedstock),
[pcre2](https://github.com/conda-forge/pcre2-feedstock),
[pixman](https://github.com/conda-forge/pixman-feedstock),
[libffi](https://github.com/conda-forge/libffi-feedstock),
[ICU](https://github.com/conda-forge/icu-feedstock),
[libjpeg-turbo](https://github.com/conda-forge/libjpeg-turbo-feedstock),
[libpng](https://github.com/conda-forge/libpng-feedstock),
[libtiff](https://github.com/conda-forge/libtiff-feedstock),
[openjpeg](https://github.com/conda-forge/openjpeg-feedstock),
[lcms2](https://github.com/conda-forge/lcms2-feedstock),
[curl](https://github.com/conda-forge/curl-feedstock),
[OpenSSL](https://github.com/conda-forge/openssl-feedstock),
[libssh2](https://github.com/conda-forge/libssh2-feedstock),
[libpsl](https://github.com/conda-forge/libpsl-feedstock),
[krb5](https://github.com/conda-forge/krb5-feedstock),
[expat](https://github.com/conda-forge/expat-feedstock),
[graphite2](https://github.com/conda-forge/graphite2-feedstock),
[libdeflate](https://github.com/conda-forge/libdeflate-feedstock),
[lerc](https://github.com/conda-forge/lerc-feedstock),
[bzip2](https://github.com/conda-forge/bzip2-feedstock),
[xz](https://github.com/conda-forge/xz-feedstock),
[zstd](https://github.com/conda-forge/zstd-feedstock),
and [zlib](https://github.com/conda-forge/zlib-feedstock).
Microsoft runtime DLLs are distributed by the upstream package and retain their own terms.

## Rebuilding the beginner ZIP

Commit the intended project changes, obtain the archive specified in
`manifest.json`, then run (Python 3.11+, Git):

```powershell
python scripts/build-release.py --poppler vendor/poppler/windows-x64.zip
```

This packages **only committed files**, injects the original verified Poppler
archive, and writes `dist/literature-reviewer-windows-x64.zip` plus its SHA256.
It never copies the working directory, virtual environment or private `data/`.
Publish the matching Poppler source and build-recipe snapshot alongside the ZIP.
