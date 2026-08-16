import { useEffect, useState } from 'react'
import { Config } from './pages/Config'
import { PrDetail } from './pages/PrDetail'
import { RepoDetail } from './pages/RepoDetail'
import { Repos } from './pages/Repos'
import { navigate, useRoute } from './router'

const THEME_KEY = 'pr-sentinel-theme'

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(
    () => localStorage.getItem(THEME_KEY)
      ?? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
  )
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])
  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')]
}

function link(path: string) {
  return {
    href: path,
    onClick: (e: React.MouseEvent) => { e.preventDefault(); navigate(path) },
  }
}

export function App() {
  const route = useRoute()
  const [theme, toggleTheme] = useTheme()

  return (
    <div className="shell">
      <header className="masthead">
        <a className="wordmark" {...link('/')}>PR Sentinel</a>
        <nav>
          <a {...link('/')} aria-current={route.name === 'repos' ? 'page' : undefined}>
            Repos
          </a>
          <a {...link('/config')} aria-current={route.name === 'config' ? 'page' : undefined}>
            Config
          </a>
          <button className="icon-button" onClick={toggleTheme}
                  aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </nav>
      </header>

      <main>
        {route.name === 'repos' && <Repos />}
        {route.name === 'config' && <Config />}
        {route.name === 'repo' && <RepoDetail owner={route.owner} repo={route.repo} />}
        {route.name === 'pr' && (
          <PrDetail owner={route.owner} repo={route.repo} pr={route.pr} />
        )}
      </main>
    </div>
  )
}
