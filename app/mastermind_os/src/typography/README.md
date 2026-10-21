# Atelier typography

Office and Projects import the original local variable fonts specified by Paper. No font request goes to a third-party service. Relative asset URLs work through the existing web and native bundlers when the components are integrated into App.

- Manrope: Google Fonts commit `8f9a401dbb3793e0d1264b15d96aa253f05280f5`, `ofl/manrope/Manrope[wght].ttf`; SHA-256 `d0639be45d0af36e798172419d7bd173c4bd4f29e2b76cbb69db1d11bf8b0a40`.
- Inter: upstream v4.1 commit `e3a3d4c57d5ecc01453a575621882a384c1995a3`, `docs/font-files/InterVariable.woff2`; SHA-256 `693b77d4f32ee9b8bfc995589b5fad5e99adf2832738661f5402f9978429a8e3`.

Both are distributed under SIL Open Font License 1.1. Their unmodified license notices and the Manrope font log live in `public/licenses/fonts`, so Vite copies them into every generated product bundle. No font files have been modified or installed into the operating system.

These assets qualify component typography. Native installation and actual browser rendering still require their separate product acceptance evidence.
