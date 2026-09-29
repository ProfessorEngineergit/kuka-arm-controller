# Vendored browser libraries

Served locally so the UI works on the Pi's Wi-Fi hotspot without internet.

| File | Package | Version | License |
|---|---|---|---|
| `three.min.js` | [three](https://www.npmjs.com/package/three) `build/three.min.js` | 0.147.0 | MIT, © three.js authors |
| `OrbitControls.js` | [three](https://www.npmjs.com/package/three) `examples/js/controls/OrbitControls.js` | 0.147.0 | MIT, © three.js authors |
| `nipplejs.js` | [nipplejs](https://www.npmjs.com/package/nipplejs) `dist/nipplejs.js` | 0.10.1 | MIT, © Yoann Moinet |

three 0.147 is the last release that still ships the non-module
`examples/js/` controls. Newer releases only have ES modules
(`examples/jsm/`), which would need a bundler or an import map.

Update: `npm pack three@<ver> nipplejs@<ver>` and copy the files above.
