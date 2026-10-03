import { useEffect, useState } from 'react'

type PromptEvent = Event & { prompt: () => Promise<void> }

/** Returns a function that shows the browser's "install app" prompt, or null when the browser doesn't offer one. */
export function useInstallPrompt(): (() => void) | null {
  const [evt, setEvt] = useState<PromptEvent | null>(null)
  useEffect(() => {
    const onPrompt = (e: Event) => { e.preventDefault(); setEvt(e as PromptEvent) }
    const onInstalled = () => setEvt(null)
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => { window.removeEventListener('beforeinstallprompt', onPrompt); window.removeEventListener('appinstalled', onInstalled) }
  }, [])
  return evt ? () => { void evt.prompt(); setEvt(null) } : null
}
