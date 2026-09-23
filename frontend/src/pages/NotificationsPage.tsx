import React from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck, ChevronRight } from 'lucide-react'
import { api, errorMessage } from '../services/api'
import { useI18n } from '../i18n'
import { fmtDateTime } from '../utils/format'
import { Badge, Card, EmptyState, ErrorBox, Loading, PageHeader, Spinner } from '../components/ui'
import type { NotificationOut } from '../types/api'

const KIND_TONE: Record<NotificationOut['kind'], string> = { INFO: 'blue', ACTION_REQUIRED: 'amber', SUCCESS: 'green', WARNING: 'red' }

export default function NotificationsPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({ queryKey: ['notifications'], queryFn: api.notifications })

  const markRead = useMutation({
    mutationFn: (id: string) => api.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
  const markAll = useMutation({
    mutationFn: api.markAllRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const open = async (n: NotificationOut) => {
    if (!n.read) {
      try {
        await markRead.mutateAsync(n.id)
      } catch {
        /* surfaced below via markRead.error */
      }
    }
    if (n.link) navigate(n.link)
  }

  if (isLoading) return <Loading label={t('common.loading')} />
  if (error || !data) return <ErrorBox message={errorMessage(error)} />

  const unread = data.filter((n) => !n.read).length

  return (
    <div>
      <PageHeader
        title={t('nav.notifications')}
        subtitle={unread ? `${unread} unread` : 'All caught up'}
        actions={
          <button className="btn-secondary" onClick={() => markAll.mutate()} disabled={markAll.isPending || unread === 0}>
            {markAll.isPending ? <Spinner /> : <CheckCheck className="h-4 w-4" />} Mark all read
          </button>
        }
      />
      {(markAll.error || markRead.error) && <div className="mb-4"><ErrorBox message={errorMessage(markAll.error || markRead.error)} /></div>}

      {data.length === 0 ? (
        <EmptyState title="No notifications" hint="Journey updates, insurer queries and recovery outcomes will appear here." />
      ) : (
        <Card>
          <ul className="-m-5 divide-y divide-ink-100">
            {data.map((n) => (
              <li key={n.id}>
                <button onClick={() => open(n)} className={`flex w-full items-start gap-3 px-5 py-4 text-left transition hover:bg-ink-50 ${n.read ? '' : 'bg-brand-50/40'}`}>
                  <div className="relative mt-0.5">
                    <Bell className={`h-4 w-4 ${n.read ? 'text-ink-300' : 'text-brand-600'}`} />
                    {!n.read && <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-white" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`text-sm ${n.read ? 'font-medium text-ink-800' : 'font-semibold text-ink-900'}`}>{n.title}</span>
                      <Badge tone={KIND_TONE[n.kind] ?? 'gray'}>{n.kind.replace(/_/g, ' ')}</Badge>
                    </div>
                    <p className="mt-0.5 text-sm text-ink-600">{n.message}</p>
                    <p className="mt-1 text-xs text-ink-400">{fmtDateTime(n.created_at)}</p>
                  </div>
                  {n.link && <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-ink-300" />}
                </button>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
