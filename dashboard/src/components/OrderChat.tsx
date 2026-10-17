import { ArrowRight, Bot, RotateCcw, Send, TriangleAlert } from 'lucide-react'
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router'
import { ApiError, api, errorText } from '../lib/api'
import { Button, PriceTag, Stamp, cx } from '../ui'

/** What POST /api/public/shops/{slug}/chat answers. */
interface ChatOrder {
  order_id: string
  status: string // buyer words: confirmed | pending_owner_approval | rejected | ...
  status_url: string
  subtotal: string
  pickup_time: string
}
interface ChatOut {
  chat_id: string
  reply: string
  orders: ChatOrder[]
  turns_left: number
}
interface Message {
  from: 'you' | 'assistant'
  text: string
}
interface Saved {
  chatId: string | null
  messages: Message[]
  orders: ChatOrder[]
}

const MAX_LEN = 500
const CHAT_TIMEOUT_MS = 70_000 // a reply can take several model and tool steps

// The chat survives a reload of this tab (the server forgets it after 30 idle minutes).
const savedKey = (slug: string) => `kampungcart.chat.${slug}`
function load(slug: string): Saved {
  try {
    const raw = sessionStorage.getItem(savedKey(slug))
    if (raw) return JSON.parse(raw) as Saved
  } catch {
    // nothing saved; fine
  }
  return { chatId: null, messages: [], orders: [] }
}
function save(slug: string, saved: Saved) {
  try {
    sessionStorage.setItem(savedKey(slug), JSON.stringify(saved))
  } catch {
    // not kept across reloads; fine
  }
}

/** The status link as a path on this site, so it opens in the app (and works on localhost). */
function statusPath(url: string): string {
  try {
    const u = new URL(url, window.location.origin)
    return u.pathname + u.search
  } catch {
    return url
  }
}

function OrderLine({ order }: { order: ChatOrder }) {
  const held = order.status === 'pending_owner_approval'
  const ok = ['confirmed', 'ready', 'done'].includes(order.status)
  return (
    <li className="flex flex-col gap-3 border-2 border-ink bg-receipt p-3 shadow-hard-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="flex flex-wrap items-center gap-3">
        <Stamp
          kind={held ? 'held' : ok ? 'approved' : 'rejected'}
          label={held ? 'Waiting for owner' : ok ? 'Confirmed' : order.status.replace(/_/g, ' ')}
          size="sm"
          animate
        />
        <span className="font-mono text-sm">
          #{order.order_id.slice(0, 8)} · <PriceTag value={order.subtotal} />
        </span>
      </div>
      <Link to={statusPath(order.status_url)} className="focus-ring inline-flex items-center gap-1 font-semibold underline underline-offset-4">
        See your order status <ArrowRight aria-hidden className="size-4" />
      </Link>
    </li>
  )
}

/** "Order with AI": the KampungCart Shop Assistant (an ADK agent on Gemini) takes the order
 *  in plain words, through the shop's own MCP tools. The order form below never depends on it. */
export function OrderChat({ slug, shopName, example }: { slug: string; shopName: string; example: string }) {
  const [saved, setSaved] = useState<Saved>(() => load(slug))
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [ended, setEnded] = useState(false)
  const listRef = useRef<HTMLOListElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const inputId = useId()
  const { messages, orders } = saved

  useEffect(() => save(slug, saved), [slug, saved])
  useEffect(() => {
    const list = listRef.current
    if (list) list.scrollTop = list.scrollHeight
  }, [messages.length, sending])

  async function send(text: string) {
    const message = text.trim()
    if (!message || sending || ended) return
    setError('')
    setSending(true)
    setDraft('')
    const asked: Saved = { ...saved, messages: [...messages, { from: 'you', text: message }] }
    setSaved(asked)
    try {
      const out = await api<ChatOut>(`/api/public/shops/${encodeURIComponent(slug)}/chat`, {
        method: 'POST',
        json: { chat_id: saved.chatId, message },
        owner: false,
        timeoutMs: CHAT_TIMEOUT_MS,
      })
      setSaved({ chatId: out.chat_id, messages: [...asked.messages, { from: 'assistant', text: out.reply }], orders: out.orders })
      if (out.turns_left <= 0) setEnded(true)
    } catch (err) {
      setError(errorText(err))
      if (err instanceof ApiError && err.status === 410) setEnded(true)
      else setDraft(message) // let them send it again
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    void send(draft)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(draft)
    }
  }

  function restart() {
    setSaved({ chatId: null, messages: [], orders: [] })
    setError('')
    setEnded(false)
    setDraft('')
    inputRef.current?.focus()
  }

  return (
    <section aria-labelledby="order-with-ai" className="flex flex-col border-2 border-ink bg-receipt shadow-hard">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b-2 border-ink bg-ink px-4 py-3 text-receipt">
        <h2 id="order-with-ai" className="flex items-center gap-2 text-xl text-receipt">
          <Bot aria-hidden className="size-5 flex-none" /> Order with AI
        </h2>
        <span className="font-mono text-xs text-turmeric">KampungCart Shop Assistant</span>
      </header>

      <div className="flex flex-col gap-4 p-4">
        {messages.length === 0 ? (
          <div className="flex flex-col gap-3">
            <p>
              Tell our assistant what you'd like from {shopName}, in your own words. It checks the menu, tells you the total, suggests pickup
              times and asks before it places anything.
            </p>
            <button
              type="button"
              onClick={() => void send(example)}
              disabled={sending}
              className="focus-ring self-start border-2 border-dashed border-ink bg-paper px-3 py-2 text-left text-sm hover:bg-turmeric-tint"
            >
              <span className="font-semibold">Try:</span> <q>{example}</q>
            </button>
          </div>
        ) : (
          <ol ref={listRef} aria-label="Chat with the shop assistant" aria-live="polite" className="flex max-h-[26rem] flex-col gap-3 overflow-y-auto pr-1">
            {messages.map((m, i) => (
              <li key={i} className={cx('flex flex-col gap-1', m.from === 'you' ? 'items-end' : 'items-start')}>
                <span className="font-mono text-xs text-muted">{m.from === 'you' ? 'You' : 'Assistant'}</span>
                <p
                  className={cx(
                    'max-w-[90%] border-2 border-ink px-3 py-2 break-words whitespace-pre-line sm:max-w-[80%]',
                    m.from === 'you' ? 'bg-turmeric-tint' : 'print-in bg-paper',
                  )}
                >
                  {m.text}
                </p>
              </li>
            ))}
            {sending && (
              <li className="flex items-center gap-2 font-mono text-sm text-ink-soft" role="status">
                <span className="inline-block size-2 animate-pulse bg-ink motion-reduce:animate-none" aria-hidden />
                Assistant is checking the menu…
              </li>
            )}
          </ol>
        )}

        {orders.length > 0 && (
          <ul aria-label="Orders from this chat" className="flex flex-col gap-2">
            {orders.map((o) => (
              <OrderLine key={o.order_id} order={o} />
            ))}
          </ul>
        )}

        {error && (
          <p role="alert" className="flex items-start gap-2 border-2 border-ink bg-turmeric-tint p-3 text-sm font-medium">
            <TriangleAlert aria-hidden className="mt-0.5 size-4 flex-none text-chili" />
            <span>{error}</span>
          </p>
        )}

        {ended ? (
          <Button variant="secondary" icon={<RotateCcw aria-hidden className="size-4" />} onClick={restart} className="self-start">
            Start a new chat
          </Button>
        ) : (
          <form onSubmit={onSubmit} className="flex flex-col gap-2">
            <label htmlFor={inputId} className="sr-only">
              Message to the shop assistant
            </label>
            <div className="flex items-end gap-2">
              <textarea
                id={inputId}
                ref={inputRef}
                rows={2}
                maxLength={MAX_LEN}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Type what you'd like…"
                className="focus-ring min-h-12 w-full min-w-0 flex-1 resize-none border-2 border-ink bg-receipt px-3 py-2"
              />
              <Button type="submit" loading={sending} disabled={!draft.trim()} icon={<Send aria-hidden className="size-4" />}>
                Send
              </Button>
            </div>
          </form>
        )}

        <p className="font-mono text-xs text-muted">
          Prices always come from the shop's menu. Pay at pickup. The AI can make mistakes: check the summary before you say yes, or order with the form
          below.
        </p>
        {messages.length > 0 && !ended && (
          <button type="button" onClick={restart} className="focus-ring self-start text-sm font-semibold underline underline-offset-4">
            Start over
          </button>
        )}
      </div>
    </section>
  )
}
