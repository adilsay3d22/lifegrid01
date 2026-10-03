import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { LockKey, PaperPlaneRight, Phone } from '@phosphor-icons/react'
import { getThread, sendMessage, sharePhone } from '../../api/client'
import { Button, QueryView, cx } from '../../components/ui'
import { fmtTime } from '../../lib/format'

/** FR-MAT-04: in-app thread; phone numbers only after both sides opt in. */
export function Component() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['thread', id], queryFn: () => getThread(id) })
  const [body, setBody] = useState('')
  const end = useRef<HTMLLIElement>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: ['thread', id] })
  const send = useMutation({ mutationFn: () => sendMessage(id, body.trim()), onSuccess: () => { setBody(''); refresh() } })
  const share = useMutation({ mutationFn: () => sharePhone(id), onSuccess: refresh })
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [q.data?.messages.length])

  return (
    <QueryView q={q} rows={5}>
      {(th) => {
        const mine = th.role === 'requester' ? th.requester_shares_phone : th.donor_shares_phone
        const theirs = th.role === 'requester' ? th.donor_shares_phone : th.requester_shares_phone
        return (
        <div className="grid gap-5">
          <header>
            <p className="font-mono text-xs text-zinc-500">{th.request_ref}</p>
            <h1 className="text-xl font-semibold tracking-tight">{t('chat.title', { area: th.hospital_area })}</h1>
          </header>

          <section aria-labelledby="phone-h" className="rounded-2xl bg-white p-4 ring-1 ring-zinc-200">
            <h2 id="phone-h" className="flex items-center gap-2 text-sm font-medium text-zinc-900">{th.counterpart_phone ? <Phone size={16} aria-hidden /> : <LockKey size={16} aria-hidden />}{t('chat.phoneTitle')}</h2>
            {th.counterpart_phone ? (
              <a href={`tel:${th.counterpart_phone.replace(/[^\d+]/g, '')}`} className="mt-2 block font-mono text-lg text-brand underline-offset-4 hover:underline">{th.counterpart_phone}</a>
            ) : (
              <>
                <ul className="mt-3 grid gap-1.5 text-sm">
                  {([['chat.you', mine], [th.role === 'requester' ? 'chat.themDonor' : th.request_ref.startsWith('AP-') ? 'chat.themHospital' : 'chat.them', theirs]] as const).map(([k, v]) => (
                    <li key={k} className="flex justify-between"><span className="text-zinc-600">{t(k)}</span><span className={v ? 'text-emerald-700' : 'text-zinc-500'}>{v ? t('chat.shared') : t('chat.notShared')}</span></li>
                  ))}
                </ul>
                {!mine && <Button size="sm" className="mt-3" loading={share.isPending} onClick={() => share.mutate()}>{t('chat.share')}</Button>}
                <p className="mt-2 text-xs text-zinc-500">{t('chat.phoneNote')}</p>
              </>
            )}
          </section>

          <ol className="grid gap-2" aria-label={t('chat.messages')} aria-live="polite">
            {th.messages.length === 0 && <li className="py-6 text-center text-sm text-zinc-500">{t('chat.empty')}</li>}
            {th.messages.map((m) => (
              <li key={m.id} className={cx('max-w-[85%] rounded-2xl px-4 py-2.5 text-sm', m.mine ? 'justify-self-end rounded-br-md bg-zinc-900 text-white' : 'justify-self-start rounded-bl-md bg-white ring-1 ring-zinc-200')}>
                <p className="break-words">{m.body}</p>
                <p className={cx('mt-1 text-right text-[11px] tabular-nums', m.mine ? 'text-zinc-400' : 'text-zinc-500')}><time dateTime={m.created_at}>{fmtTime(m.created_at)}</time></p>
              </li>
            ))}
            <li ref={end} aria-hidden />
          </ol>

          <form onSubmit={(e) => { e.preventDefault(); if (body.trim()) send.mutate() }} className="sticky bottom-20 flex items-end gap-2 rounded-2xl bg-white p-2 ring-1 ring-zinc-200 focus-within:ring-2 focus-within:ring-brand shadow-[0_8px_24px_-12px_rgb(24_24_27/0.2)]">
            <label htmlFor="msg" className="sr-only">{t('chat.message')}</label>
            <textarea id="msg" name="message" value={body} onChange={(e) => setBody(e.target.value.slice(0, 1000))} rows={1} placeholder={t('chat.placeholder')}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (body.trim()) send.mutate() } }}
              className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-base outline-none placeholder:text-zinc-500" />
            <Button type="submit" variant="primary" disabled={!body.trim()} loading={send.isPending} aria-label={t('chat.send')} className="size-10 px-0"><PaperPlaneRight size={18} weight="fill" aria-hidden /></Button>
          </form>
        </div>
        )
      }}
    </QueryView>
  )
}
