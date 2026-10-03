import type { Abo, CompatRule, Component, Rh } from '../api/types'

// Seed values for the mock compat_rule table (spec section 6). The real values live server-side in rule tables.
const RED_CELLS: Record<string, string[]> = {
  'O-': ['O-'],
  'O+': ['O+', 'O-'],
  'A-': ['A-', 'O-'],
  'A+': ['A+', 'A-', 'O+', 'O-'],
  'B-': ['B-', 'O-'],
  'B+': ['B+', 'B-', 'O+', 'O-'],
  'AB-': ['AB-', 'A-', 'B-', 'O-'],
  'AB+': ['AB+', 'AB-', 'A+', 'A-', 'B+', 'B-', 'O+', 'O-'],
}
const PLASMA: Record<Abo, Abo[]> = { O: ['O', 'A', 'B', 'AB'], A: ['A', 'AB'], B: ['B', 'AB'], AB: ['AB'] }

export const ABOS: Abo[] = ['O', 'A', 'B', 'AB']
export const RHS: Rh[] = ['pos', 'neg']
export const COMPONENTS: Component[] = ['red_cells', 'platelets', 'plasma']
export const GROUPS: [Abo, Rh][] = ABOS.flatMap((a) => RHS.map((r) => [a, r] as [Abo, Rh]))

export const groupLabel = (abo: Abo | null, rh: Rh | null) => (abo ? `${abo}${rh === 'neg' ? '−' : rh === 'pos' ? '+' : ''}` : '?')
const parse = (g: string): [Abo, Rh] => [g.slice(0, -1) as Abo, g.endsWith('-') ? 'neg' : 'pos']

export function seedCompatRules(): CompatRule[] {
  const rules: CompatRule[] = []
  for (const [rec, donors] of Object.entries(RED_CELLS)) {
    const [ra, rr] = parse(rec)
    donors.forEach((d, i) => {
      const [da, dr] = parse(d)
      rules.push({ component: 'red_cells', recipient_abo: ra, recipient_rh: rr, donor_abo: da, donor_rh: dr, rank: i + 1 })
    })
  }
  // Plasma ignores Rh: stored with both pos and neg rows so lookups stay uniform (spec section 11 notes).
  for (const [ra, donors] of Object.entries(PLASMA) as [Abo, Abo[]][]) {
    for (const rr of RHS) for (const dr of RHS) donors.forEach((da, i) =>
      rules.push({ component: 'plasma', recipient_abo: ra, recipient_rh: rr, donor_abo: da, donor_rh: dr, rank: i + 1 }))
  }
  // Platelets: ABO-identical first, Rh match preferred, out-of-group allowed (config defaults).
  for (const [ra, rr] of GROUPS) {
    const ranked = GROUPS.map(([da, dr]) => ({ da, dr, score: (da === ra ? 0 : 2) + (dr === rr ? 0 : 1) })).sort((a, b) => a.score - b.score)
    ranked.forEach(({ da, dr }, i) =>
      rules.push({ component: 'platelets', recipient_abo: ra, recipient_rh: rr, donor_abo: da, donor_rh: dr, rank: i + 1 }))
  }
  return rules
}

export const SHELF_DAYS: Record<Component, number> = { red_cells: 42, platelets: 5, plasma: 365 }
export const CONSENT_VERSION = 'v1.2'
