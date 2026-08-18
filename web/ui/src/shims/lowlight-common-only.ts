// Build-time shim aliased over the `lowlight` package (see vite.config.ts).
//
// @git-diff-view/core hard-imports `all` from lowlight — every highlight.js
// grammar, ~200 languages, which alone pushed the lazy diff chunk past
// 300 kB gzipped. The dashboard reviews application code, so the `common`
// set (~37 languages) is plenty; re-exporting it under the `all` name lets
// the bundler tree-shake the rest. Deep relative imports bypass the alias.
export { grammars as all } from '../../node_modules/lowlight/lib/common.js'
export { grammars as common } from '../../node_modules/lowlight/lib/common.js'
export { createLowlight } from '../../node_modules/lowlight/lib/index.js'
