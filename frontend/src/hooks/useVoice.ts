import { useCallback, useRef, useState } from 'react'
import { api, errorMessage } from '../services/api'

/** Browser microphone → FastAPI → Sarvam speech-to-text → text. */
export function useVoice(language?: string) {
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])

  const start = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : undefined })
      chunks.current = []
      mr.ondataavailable = (e) => e.data.size && chunks.current.push(e.data)
      mr.start()
      recorder.current = mr
      setRecording(true)
    } catch (e) {
      setError('Microphone access was denied or is unavailable.')
    }
  }, [])

  const stop = useCallback(
    () =>
      new Promise<string>((resolve) => {
        const mr = recorder.current
        if (!mr) return resolve('')
        mr.onstop = async () => {
          mr.stream.getTracks().forEach((t) => t.stop())
          setRecording(false)
          setBusy(true)
          try {
            const blob = new Blob(chunks.current, { type: mr.mimeType || 'audio/webm' })
            const res = await api.transcribe(blob, language)
            resolve(res.transcript || '')
          } catch (e) {
            setError(errorMessage(e))
            resolve('')
          } finally {
            setBusy(false)
          }
        }
        mr.stop()
      }),
    [language],
  )

  return { recording, busy, error, start, stop, supported: typeof window !== 'undefined' && !!navigator.mediaDevices }
}

export async function speak(text: string, language: string): Promise<boolean> {
  try {
    const res = await api.speak(text, language)
    const audio = new Audio(`data:audio/wav;base64,${res.audio_base64}`)
    await audio.play()
    return true
  } catch {
    return false
  }
}
