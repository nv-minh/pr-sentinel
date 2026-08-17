/* The interface dictionary. English is the source of truth for the key set:
   `vi` is typed as Record<keyof typeof en, string>, so a key added here and
   forgotten there is a `tsc -b` error, and `npm run build` runs tsc first.

   Status vocabulary (PASS, STALE, BREAKING_API_CHANGE …) is absent on purpose:
   those are enum values from the findings schema, they appear verbatim in the
   comment posted to GitHub, and a translated dashboard label would no longer
   match the pull request it describes. */

const en = {
  'nav.repos': 'Repos',
  'nav.config': 'Config',
  'nav.themeLight': 'Light',
  'nav.themeDark': 'Dark',
  'nav.themeSwitchToLight': 'Switch to light theme',
  'nav.themeSwitchToDark': 'Switch to dark theme',
  'nav.langSwitchToVi': 'Chuyển giao diện sang tiếng Việt',
  'nav.langSwitchToEn': 'Switch interface to English',
  'repos.bugs': '{n} bugs',
  'gate.pass': 'Clear to merge',
  'gate.warn': 'Merge with care',
  'gate.fail': 'Blocked',
  'gate.unknown': 'Not scored',
  'band.empty': 'No scored reviews yet',
  'common.loading': 'Loading',
  'common.yes': 'yes',
  'common.no': 'no',
  'common.noTitle': '(no title)',
  'citations.none': 'no evidence cited',
}

const vi: Record<keyof typeof en, string> = {
  'nav.repos': 'Kho mã',
  'nav.config': 'Cấu hình',
  'nav.themeLight': 'Sáng',
  'nav.themeDark': 'Tối',
  'nav.themeSwitchToLight': 'Chuyển sang giao diện sáng',
  'nav.themeSwitchToDark': 'Chuyển sang giao diện tối',
  'nav.langSwitchToVi': 'Chuyển giao diện sang tiếng Việt',
  'nav.langSwitchToEn': 'Switch interface to English',
  'repos.bugs': '{n} lỗi',
  'gate.pass': 'Sẵn sàng merge',
  'gate.warn': 'Merge có cân nhắc',
  'gate.fail': 'Bị chặn',
  'gate.unknown': 'Chưa chấm điểm',
  'band.empty': 'Chưa có review nào được chấm điểm',
  'common.loading': 'Đang tải',
  'common.yes': 'có',
  'common.no': 'không',
  'common.noTitle': '(không có tiêu đề)',
  'citations.none': 'không có bằng chứng nào được dẫn',
}

export type Key = keyof typeof en
export type Vars = Record<string, string | number>

// Annotated rather than inferred so TABLES[lang][key] is `string`, not the
// union of en's literal types with vi's `string`.
export const TABLES: Record<'en' | 'vi', Record<Key, string>> = { en, vi }

/** Phase and metric labels arrive from the server at runtime (see
 *  web/metrics.py PHASES), so unlike everything above they cannot be a total
 *  map checked by the compiler. An id with no entry falls back to the server's
 *  English string. tests/test_ui_strings.py is what stops that going unnoticed. */
export function lookup(lang: 'en' | 'vi', key: string, fallback: string): string {
  const table = TABLES[lang] as Record<string, string | undefined>
  return table[key] ?? fallback
}
