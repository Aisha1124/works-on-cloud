import { ArrowLeft } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router'
import { api } from '../lib/api'
import { useLoad } from '../lib/hooks'
import { ReceiptCard, ReceiptDivider, buttonClass } from '../ui'

interface SiteInfo {
  admin_email: string
  retention_days: number
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-2xl">{title}</h2>
      {children}
    </section>
  )
}

/** What KampungCart collects, why, for how long, and how to ask for deletion. Every line here
 *  describes what the code does (see backend/privacy.py for the 90-day erase). */
export function Privacy() {
  const site = useLoad((signal) => api<SiteInfo>('/api/public/site', { owner: false, signal }), 'site')
  const days = site.data?.retention_days ?? 90
  const email = site.data?.admin_email ?? ''

  useEffect(() => {
    document.title = 'Privacy · KampungCart'
  }, [])

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 pt-6 pb-16 sm:pt-10">
      <ReceiptCard aria-labelledby="privacy-heading">
        <h1 id="privacy-heading" className="text-4xl">
          Privacy
        </h1>
        <p className="mt-2 text-ink-soft">How KampungCart handles your details, in plain words.</p>
        <ReceiptDivider />
        <div className="flex flex-col gap-6 pb-6">
          <Section title="What we collect">
            <ul className="list-[square] pl-5">
              <li>
                <b>When you order:</b> your name, phone number, pickup time, the items, your note to the shop, and your email if you choose to give it.
              </li>
              <li>
                <b>When you run a shop:</b> your email, your shop details and the menu photos you upload. Photos are cleaned first, so the location stored in a phone photo is removed.
              </li>
              <li>
                <b>Your device's internet address</b>, only to stop too many orders or sign-in attempts from one place. It is kept scrambled, for an hour at most.
              </li>
            </ul>
            <p>We never ask for card or bank details. You pay the shop at pickup.</p>
          </Section>

          <Section title="Why, and who sees it">
            <ul className="list-[square] pl-5">
              <li>Your name and phone are only shared with the shop you order from, so they can prepare your order and reach you about the pickup.</li>
              <li>Your email is only used to send you updates about that order (confirmed, rejected, expired or cancelled).</li>
              <li>AI assistants that order for you never get your phone number back from us. Order emails to the shop show only its last 4 digits.</li>
              <li>To help the shop spot unusual orders, your note may be sent to Google's Gemini AI to write a one-line explanation for the owner. Gemini also reads the menu photos shop owners upload.</li>
              <li>Data is stored on Google Cloud, and emails are sent through Google's Gmail service.</li>
              <li>We don't sell your details or use them for advertising.</li>
            </ul>
          </Section>

          <Section title="How long we keep it">
            <p>
              {days} days after the pickup time, your name, phone number, email and note are erased from the order automatically. The items and totals stay, so the shop's records still add up.
            </p>
            <p>A shop's own details stay while the shop is on KampungCart.</p>
          </Section>

          <Section title="Ask us to delete your details">
            {email ? (
              <p>
                Email{' '}
                <a className="focus-ring font-mono font-semibold break-all underline" href={`mailto:${email}`}>
                  {email}
                </a>{' '}
                with your order link (or your shop name). We'll delete your details and tell you when it's done.
              </p>
            ) : (
              <p>Contact the shop you ordered from. They can pass your request to us.</p>
            )}
          </Section>
        </div>
      </ReceiptCard>
      <Link to="/" className={buttonClass('ghost', 'md', 'self-start')}>
        <ArrowLeft aria-hidden className="size-4" /> KampungCart home
      </Link>
    </main>
  )
}
