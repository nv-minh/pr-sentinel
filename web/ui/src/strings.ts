/* The interface dictionary. English is the source of truth for the key set:
   `vi` is typed as Record<keyof typeof en, string>, so a key added here and
   forgotten there is a `tsc -b` error, and `npm run build` runs tsc first.

   Status vocabulary (PASS, STALE, BREAKING_API_CHANGE …) is absent on purpose:
   those are enum values from the findings schema, they appear verbatim in the
   comment posted to GitHub, and a translated dashboard label would no longer
   match the pull request it describes.

   Repo mode values (`auto`, `manual`) are absent for the same reason: they are
   the literal values an operator writes in prsentinel.yml and picks from
   Config.tsx's mode select, so Repos.tsx's "AUTO" badge (repos with no data
   yet) stays English rather than disagreeing with the YAML and the dropdown
   it mirrors. */

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
  'repos.error': 'Could not load repos — {detail}',
  'repos.loading': 'Loading repositories',
  'repos.title': 'Every claim, checked against the code.',
  'repos.subOne': '{n} repo reviewed',
  'repos.subMany': '{n} repos reviewed',
  'repos.subPrs': '{n} pull requests on the record',
  'repos.reviewedHeading': 'Reviewed repositories',
  'repos.emptyBefore': 'No reviews yet. Run ',
  'repos.emptyAfter': ', or add a repo on the Config page and let the poller pick it up.',
  'repos.prs': '{n} PR',
  'repos.docErrors': '{n} doc errors',
  'repos.breaking': '{n} breaking',
  'repos.testGaps': '{n} test gaps',
  'repos.verified': '{score} verified',
  'repos.waitingHeading': 'Watched, not yet reviewed',
  'repos.waitingMeta': 'Set to auto — the poller reviews its next open PR',
  'repo.loading': 'Loading repository',
  'repo.statusReviewed': 'Reviewed',
  'repo.statusReviewing': 'Reviewing now',
  'repo.statusNotReviewed': 'Not reviewed',
  'repo.tilePrs': 'PRs reviewed',
  'repo.tileVerified': 'Verified',
  'repo.tileVerifiedNote': 'claims backed by file:line',
  'repo.tileBugs': 'Bugs',
  'repo.tileBugsNote': 'failed claims + broken impact',
  'repo.tileDocErrors': 'Doc errors',
  'repo.tileBreaking': 'Breaking',
  'repo.tileBreakingNote': 'API + schema contracts',
  'repo.tileSpent': 'Spent',
  'repo.gateHeading': 'Merge decisions',
  'repo.openPrsHeading': 'Open pull requests',
  'repo.unreachable': 'GitHub is unreachable — showing pull requests from stored reviews only.',
  'repo.noOpenPrs': 'No open pull requests.',
  'repo.draft': 'draft',
  'repo.roundOne': '{n} round',
  'repo.roundMany': '{n} rounds',
  'repo.prBugs': '{n} bugs',
  'repo.prDocErrors': '{n} doc errors',
  'repo.prBreaking': '{n} breaking',
  'repo.reReview': 'Re-review',
  'repo.reviewNow': 'Review now',
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
  'repos.error': 'Không tải được danh sách kho mã — {detail}',
  'repos.loading': 'Đang tải danh sách kho mã',
  'repos.title': 'Mọi tuyên bố đều được đối chiếu với code.',
  'repos.subOne': '{n} kho mã đã review',
  'repos.subMany': '{n} kho mã đã review',
  'repos.subPrs': '{n} pull request trong hồ sơ',
  'repos.reviewedHeading': 'Kho mã đã review',
  'repos.emptyBefore': 'Chưa có review nào. Chạy ',
  'repos.emptyAfter': ', hoặc thêm một kho mã ở trang Cấu hình rồi để bộ quét tự nhận.',
  'repos.prs': '{n} PR',
  'repos.docErrors': '{n} lỗi tài liệu',
  'repos.breaking': '{n} phá vỡ tương thích',
  'repos.testGaps': '{n} lỗ hổng test',
  'repos.verified': '{score} đã xác minh',
  'repos.waitingHeading': 'Đang theo dõi, chưa review',
  'repos.waitingMeta': 'Đặt chế độ auto — bộ quét sẽ review PR mở tiếp theo',
  'repo.loading': 'Đang tải kho mã',
  'repo.statusReviewed': 'Đã review',
  'repo.statusReviewing': 'Đang review',
  'repo.statusNotReviewed': 'Chưa review',
  'repo.tilePrs': 'PR đã review',
  'repo.tileVerified': 'Đã xác minh',
  'repo.tileVerifiedNote': 'tuyên bố có dẫn file:line',
  'repo.tileBugs': 'Lỗi',
  'repo.tileBugsNote': 'tuyên bố sai + tác động hỏng',
  'repo.tileDocErrors': 'Lỗi tài liệu',
  'repo.tileBreaking': 'Phá vỡ tương thích',
  'repo.tileBreakingNote': 'hợp đồng API + schema',
  'repo.tileSpent': 'Đã chi',
  'repo.gateHeading': 'Quyết định merge',
  'repo.openPrsHeading': 'Pull request đang mở',
  'repo.unreachable': 'Không kết nối được GitHub — chỉ hiện pull request từ review đã lưu.',
  'repo.noOpenPrs': 'Không có pull request nào đang mở.',
  'repo.draft': 'nháp',
  'repo.roundOne': '{n} vòng',
  'repo.roundMany': '{n} vòng',
  'repo.prBugs': '{n} lỗi',
  'repo.prDocErrors': '{n} lỗi tài liệu',
  'repo.prBreaking': '{n} phá vỡ tương thích',
  'repo.reReview': 'Review lại',
  'repo.reviewNow': 'Review ngay',
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
