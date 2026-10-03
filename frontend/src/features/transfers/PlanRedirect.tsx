import { Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { listPlans } from '../../api/client'
import { QueryView } from '../../components/ui'

export function Component() {
  const q = useQuery({ queryKey: ['plans'], queryFn: listPlans })
  return <QueryView q={q}>{(plans) => <Navigate to={`/staff/plans/${plans[0].id}`} replace />}</QueryView>
}
