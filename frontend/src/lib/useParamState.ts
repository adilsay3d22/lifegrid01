import { useSearchParams } from 'react-router-dom'

/** useState backed by a URL query param, so tabs and filters deep-link. Default values stay out of the URL. */
export function useParamState<T extends string>(key: string, initial: T): [T, (v: T) => void] {
  const [params, setParams] = useSearchParams()
  const value = (params.get(key) ?? initial) as T
  const set = (v: T) => setParams((p) => { if (v === initial) p.delete(key); else p.set(key, v); return p }, { replace: true })
  return [value, set]
}
