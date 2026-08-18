import type { PrDetail, PrExtras } from '../api'
import { Empty, Eyebrow, Ledger, Notice, Row, StatusWord, Tile, Tiles } from '../components'
import { useT } from '../i18n'
import { formatCost, formatScore } from '../status'
import type { Key } from '../strings'

export function OverviewTab({ data, extras }: { data: PrDetail; extras: PrExtras | null }) {
  const t = useT()
  const rec = data.pr
  const score = data.score ?? {}
  const gate = score.gate ?? 'unknown'
  const ticket = extras?.ticket
  const description = extras?.description
  const neutralized = extras?.neutralized ?? []

  return (
    <div className="grid gap-1">
      <Tiles>
        <Tile label={t('pr.tileGate')} value={<StatusWord status={gate} />}
              note={t(`gate.${gate}` as Key)} />
        <Tile label={t('pr.tileVerified')}
              value={formatScore(score.verification_score ?? rec?.verification_score)}
              note={t('pr.tileVerifiedNote')} />
        <Tile label={t('pr.tileVerdict')} value={<StatusWord status={rec?.verdict ?? ''} />}
              note={t('pr.tileVerdictNote')} />
        <Tile label={t('pr.tileRisk')} value={score.business_risk ?? '—'} />
        <Tile label={t('pr.tileRounds')} value={rec?.rounds ?? 1} />
        <Tile label={t('pr.tileCost')} value={formatCost(rec?.cost_usd)} />
      </Tiles>

      {neutralized.length > 0 && (
        <Notice tone="fail">
          {t('extras.neutralizedBanner')}
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5 font-mono text-xs">
            {neutralized.flatMap((n) => n.items.map((item, i) => (
              <li key={`${n.phase}-${i}`}>{n.phase}: {item}</li>
            )))}
          </ul>
        </Notice>
      )}

      {ticket?.primary ? (
        <>
          <Eyebrow>{t('extras.ticketHeading')}</Eyebrow>
          <Ledger>
            {(ticket.tickets ?? []).map((tk, i) => {
              const row = tk as Record<string, string>
              return (
                <Row key={i} status={row.key === ticket.primary ? 'PASS' : 'UNVERIFIED'}
                     title={<a className="text-brand hover:underline" href={row.url}>{row.key} — {row.summary}</a>}
                     meta={[row.status, row.type, row.priority].filter(Boolean).join(' · ')} />
              )
            })}
          </Ledger>
        </>
      ) : null}

      {description?.description ? (
        <>
          <Eyebrow>{t('extras.descriptionHeading')}</Eyebrow>
          <p className="max-w-[72ch] whitespace-pre-wrap text-[13px] leading-relaxed text-ink-muted">
            {description.description}
          </p>
        </>
      ) : null}

      <Eyebrow>{t('ws.questionsHeading')}</Eyebrow>
      <Ledger>
        {(data.questions ?? []).map((q, i) => (
          <Row key={`q-${i}`} status="UNVERIFIED" title={q} />
        ))}
        {(data.answers ?? []).map((a, i) => (
          <Row key={`a-${i}`} status={a.answer === 'SKIPPED' ? 'UNVERIFIED' : 'PASS'}
               title={a.question} meta={t('pr.answered', { answer: a.answer })} right={a.kind} />
        ))}
        {!(data.questions?.length || data.answers?.length) && (
          <Empty>{t('pr.emptyConfirm')}</Empty>
        )}
      </Ledger>

      {data.replies && data.replies.length > 0 && (
        <>
          <Eyebrow>{t('pr.repliesHeading')}</Eyebrow>
          <Ledger>
            {data.replies.map((r, i) => (
              <Row key={i} status="PASS" title={r.body}
                   meta={`${r.author} · ${r.source}`} right={r.created_at?.slice(0, 10)} />
            ))}
          </Ledger>
        </>
      )}

      {data.pruned && data.pruned.length > 0 && (
        <>
          <Eyebrow>{t('ws.prunedHeading')}</Eyebrow>
          <Ledger>
            {data.pruned.map((p, i) => (
              <Row key={i} status={p.dropped ? 'UNVERIFIED' : 'PARTIAL'} title={p.filename}
                   meta={p.reason} right={p.dropped ? t('pr.dropped') : t('pr.trimmed')} />
            ))}
          </Ledger>
        </>
      )}

      {data.siblings?.siblings?.length ? (
        <>
          <Eyebrow>{t('pr.tabCrossPr')}</Eyebrow>
          <Ledger>
            {data.siblings.siblings.map((s) => (
              <Row key={s.pr} status="UNVERIFIED"
                   title={<a className="text-brand hover:underline" href={s.url}>#{s.pr} {s.title}</a>}
                   meta={`${s.author} · ${(s.overlap_paths ?? []).join(', ')}`}
                   right={s.overlap} />
            ))}
          </Ledger>
        </>
      ) : null}
    </div>
  )
}
