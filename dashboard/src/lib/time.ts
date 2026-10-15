const sg = { timeZone: 'Asia/Singapore' } as const

const pickupFmt = new Intl.DateTimeFormat('en-SG', {
  ...sg,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

const stampFmt = new Intl.DateTimeFormat('en-SG', {
  ...sg,
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

/** "Sat, 17 Oct, 10:00" in Singapore time. */
export function formatPickup(iso: string): string {
  return pickupFmt.format(new Date(iso))
}

/** "15 Oct, 14:02" in Singapore time. */
export function formatStamp(iso: string): string {
  return stampFmt.format(new Date(iso))
}
