import { Camera, ImageUp } from 'lucide-react'
import { useId, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { buttonClass, cx } from '../ui'

export const MAX_PHOTOS = 5
const MAX_BYTES = 15 * 1024 * 1024

/** Drag/drop, pick or snap 1-5 menu photos. Checks count, type and size before upload. */
export function PhotoDrop({
  onFiles,
  compact = false,
  title = 'Drop your menu photo here',
}: {
  onFiles: (files: File[]) => void
  compact?: boolean
  title?: ReactNode
}) {
  const pickRef = useRef<HTMLInputElement>(null)
  const cameraRef = useRef<HTMLInputElement>(null)
  const [drag, setDrag] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const hintId = useId()

  function accept(list: FileList | null) {
    const files = Array.from(list ?? [])
    if (!files.length) return
    if (files.length > MAX_PHOTOS) return setProblem(`Up to ${MAX_PHOTOS} photos at a time, please.`)
    if (files.some((f) => !f.type.startsWith('image/') && !/\.(heic|heif)$/i.test(f.name)))
      return setProblem('That file is not a photo. Use a JPG, PNG, WEBP or HEIC picture.')
    if (files.some((f) => f.size > MAX_BYTES)) return setProblem('Each photo must be 15 MB or smaller.')
    setProblem(null)
    onFiles(files)
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDrag(false)
    accept(e.dataTransfer.files)
  }

  return (
    <div className="flex flex-col gap-3">
      <div
        className={cx('dropzone relative flex flex-col items-center justify-center gap-4 text-center', compact ? 'p-5' : 'min-h-64 p-5 sm:min-h-96 sm:p-10')}
        data-drag={drag || undefined}
        onDragOver={(e) => {
          e.preventDefault()
          setDrag(true)
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        {!compact && (
          <span aria-hidden className="grid size-20 place-items-center border-2 border-ink bg-turmeric shadow-hard sm:size-24">
            <ImageUp className="size-10 sm:size-12" strokeWidth={2.25} />
          </span>
        )}
        <div>
          <p className={cx('font-display font-extrabold', compact ? 'text-xl' : 'text-2xl sm:text-4xl')}>{title}</p>
          <p id={hintId} className="mt-1 text-ink-soft">
            A clear, straight-on photo of your price list or menu. Up to {MAX_PHOTOS} photos.
          </p>
        </div>
        <div className="flex flex-wrap justify-center gap-3">
          <button
            type="button"
            className={buttonClass('primary', compact ? 'md' : 'lg')}
            aria-describedby={hintId}
            onClick={() => pickRef.current?.click()}
          >
            <ImageUp aria-hidden className="size-5" /> Choose photo
          </button>
          {/* Phones open the camera straight away. */}
          <button
            type="button"
            className={buttonClass('secondary', compact ? 'md' : 'lg', 'sm:hidden')}
            onClick={() => cameraRef.current?.click()}
          >
            <Camera aria-hidden className="size-5" /> Take photo
          </button>
        </div>
        <input
          ref={pickRef}
          type="file"
          accept="image/*,.heic,.heif"
          multiple
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => {
            accept(e.target.files)
            e.target.value = ''
          }}
        />
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => {
            accept(e.target.files)
            e.target.value = ''
          }}
        />
      </div>
      {problem && (
        <p role="alert" className="border-2 border-ink border-l-8 border-l-chili bg-receipt px-3 py-2 font-semibold">
          {problem}
        </p>
      )}
    </div>
  )
}
