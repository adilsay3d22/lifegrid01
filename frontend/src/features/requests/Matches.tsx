import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getThread, listRequestMatches, recordMatchOutcome, sendMessage } from '../../api/client'
import { Badge, Button, Dialog, GroupChip, inputCls, type Tone } from '../../components/ui'
import { fmtTime } from '../../lib/format'
import { groupLabel } from '../../lib/rules'

const TONE: Record<string, Tone> = { invited: 'neutral', accepted: 'info', donated: 'good', declined: 'neutral', expired: 'neutral', no_show: 'bad', deferred_on_site: 'warn', withdrawn: 'neutral' }

/** Donors invited for a request: reference and group only, never contact details. Staff record outcomes (FR-MAT-07). */
export function RequestMatches({ requestId, canRecord, canMessage }: { requestId: string; canRecord: boolean; canMessage?: boolean }) {
  const { t } = useTranslation()
  const [chat, setChat] = useState<string | null>(null)
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['matches', requestId], queryFn: () => listRequestMatches(requestId) })
  const m = useMutation({
    mutationFn: ({ id, outcome }: { id: string; outcome: 'donated' | 'no_show' | 'deferred_on_site' }) => recordMatchOutcome(id, outcome),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['matches', requestId] }); qc.invalidateQueries({ queryKey: ['requests'] }) },
  })
  if (!q.data?.length) return null
  const shown = q.data.filter((x) => x.status !== 'invited').concat(q.data.filter((x) => x.status === 'invited')).slice(0, 12)
  return (
    <section aria-labelledby={`m-${requestId}`} className="grid gap-2">
      <h3 id={`m-${requestId}`} className="text-sm font-semibold">{t('matches.title', { count: q.data.length })}</h3>
      <ul className="max-h-64 divide-y divide-zinc-100 overflow-y-auto rounded-xl ring-1 ring-zinc-200">
        {shown.map((x) => (
          <li key={x.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
            <GroupChip label={groupLabel(x.abo, x.rh)} verified={x.group_verified} />
            <span className="font-mono text-xs">{x.donor_ref}</span>
            <span className="text-xs text-zinc-500">{t('matches.wave', { n: x.wave })}</span>
            <span className="ml-auto flex items-center gap-2">
              {canMessage && (x.status === 'accepted' || x.status === 'donated') && <Button size="sm" variant="ghost" onClick={() => setChat(x.id)}>{t('matches.message')}</Button>}
              <Badge tone={TONE[x.status]}>{t(`matchStatus.${x.status}`)}</Badge>
            </span>
            {canRecord && x.status === 'accepted' && (
              <span className="flex w-full justify-end gap-1">
                {(['donated', 'no_show', 'deferred_on_site'] as const).map((o) => (
                  <Button key={o} size="sm" variant={o === 'donated' ? 'primary' : 'ghost'} loading={m.isPending && m.variables?.id === x.id && m.variables.outcome === o}
                    onClick={() => m.mutate({ id: x.id, outcome: o })}>{t(`matchStatus.${o}`)}</Button>
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
      {chat && <StaffThread matchId={chat} onClose={() => setChat(null)} />}
    </section>
  )
}

/** The staff member who started an appeal talks to donors who accepted. Phones stay masked unless both opt in. */
function StaffThread({ matchId, onClose }: { matchId: string; onClose: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [body, setBody] = useState('')
  const q = useQuery({ queryKey: ['thread', matchId], queryFn: () => getThread(matchId), refetchInterval: 10_000 })
  const send = useMutation({ mutationFn: () => sendMessage(matchId, body.trim()), onSuccess: () => { setBody(''); qc.invalidateQueries({ queryKey: ['thread', matchId] }) } })
  return (
    <Dialog open onClose={onClose} title={t('matches.chatTitle')} description={q.data?.request_ref}>
      <ol className="grid max-h-72 gap-2 overflow-y-auto" aria-label={t('chat.messages')}>
        {q.data?.messages.length === 0 && <li className="py-4 text-center text-sm text-zinc-500">{t('chat.empty')}</li>}
        {q.data?.messages.map((m) => (
          <li key={m.id} className={m.mine ? 'max-w-[85%] justify-self-end rounded-2xl rounded-br-md bg-zinc-900 px-3 py-2 text-sm text-white' : 'max-w-[85%] justify-self-start rounded-2xl rounded-bl-md bg-zinc-100 px-3 py-2 text-sm'}>
            <p className="break-words">{m.body}</p><p className="mt-0.5 text-right text-[11px] opacity-70">{fmtTime(m.created_at)}</p>
          </li>
        ))}
      </ol>
      <form onSubmit={(e) => { e.preventDefault(); if (body.trim()) send.mutate() }} className="flex gap-2">
        <label htmlFor={`msg-${matchId}`} className="sr-only">{t('chat.message')}</label>
        <input id={`msg-${matchId}`} value={body} onChange={(e) => setBody(e.target.value.slice(0, 1000))} placeholder={t('chat.placeholder')} className={inputCls} autoComplete="off" />
        <Button type="submit" variant="primary" loading={send.isPending} disabled={!body.trim()}>{t('chat.send')}</Button>
      </form>
    </Dialog>
  )
}
