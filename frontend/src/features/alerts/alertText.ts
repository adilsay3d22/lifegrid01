import type { TFunction } from 'i18next'
import type { Alert } from '../../api/types'

export const alertText = (t: TFunction, a: Alert) =>
  t(`alerts.text.${a.type}`, { ...a.payload, component: a.payload.component ? t(`component.${a.payload.component}`) : '' })
