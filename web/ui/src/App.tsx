import { Config } from './pages/Config'
import { Workspace } from './workspace/Workspace'
import { RepoDetail } from './pages/RepoDetail'
import { Repos } from './pages/Repos'
import { useLang, useT } from './i18n'
import { Link, useRoute } from './router'
import { useTheme } from './theme'

const NAV_LINK =
  'font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted ' +
  'hover:text-ink aria-[current=page]:text-ink'

export function App() {
  const route = useRoute()
  const [theme, toggleTheme] = useTheme()
  const [lang, setLang] = useLang()
  const t = useT()

  // The review workspace runs three panes wide; every other route keeps the
  // centred reading column.
  const wide = route.name === 'pr'
  return (
    <div className={wide
      ? 'px-6 pb-16 max-[620px]:px-4'
      : 'mx-auto max-w-[1120px] px-7 pb-24 max-[620px]:px-4 max-[620px]:pb-16'}>
      <header className="mb-8 flex flex-wrap items-baseline gap-5 border-b border-hairline-strong pt-[22px] pb-[18px]">
        <Link to="/" className="font-mono text-[13px] font-bold uppercase tracking-[0.14em] text-brand">
          PR Sentinel
        </Link>
        <nav className="ml-auto flex items-center gap-[18px]">
          <Link to="/" className={NAV_LINK}
                aria-current={route.name === 'repos' ? 'page' : undefined}>
            {t('nav.repos')}
          </Link>
          <Link to="/config" className={NAV_LINK}
                aria-current={route.name === 'config' ? 'page' : undefined}>
            {t('nav.config')}
          </Link>
          <button
            className="rounded border border-hairline-strong px-[9px] py-1 font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted hover:border-ink-muted hover:text-ink"
            onClick={() => setLang(lang === 'vi' ? 'en' : 'vi')}
            aria-label={lang === 'vi' ? t('nav.langSwitchToEn') : t('nav.langSwitchToVi')}
            lang={lang === 'vi' ? 'en' : 'vi'}
          >
            {lang === 'vi' ? 'EN' : 'VI'}
          </button>
          <button
            className="rounded border border-hairline-strong px-[9px] py-1 font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted hover:border-ink-muted hover:text-ink"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? t('nav.themeSwitchToLight') : t('nav.themeSwitchToDark')}
          >
            {theme === 'dark' ? t('nav.themeLight') : t('nav.themeDark')}
          </button>
        </nav>
      </header>

      <main>
        {route.name === 'repos' && <Repos />}
        {route.name === 'config' && <Config />}
        {route.name === 'repo' && <RepoDetail owner={route.owner} repo={route.repo} />}
        {route.name === 'pr' && (
          <Workspace owner={route.owner} repo={route.repo} pr={route.pr} />
        )}
      </main>
    </div>
  )
}
