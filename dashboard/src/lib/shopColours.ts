// The preset header colours an owner can pick for the public shop page. The backend only
// accepts these names (ShopColour in backend/models.py). Every colour keeps the receipt-white
// signboard text at WCAG AA contrast (4.9:1 or more).

export type ShopColour = 'chili' | 'pandan' | 'kopi' | 'laut' | 'bunga' | 'charcoal'

export const DEFAULT_SHOP_COLOUR: ShopColour = 'chili'

export const SHOP_COLOURS: { value: ShopColour; label: string; hex: string }[] = [
  { value: 'chili', label: 'Chili red', hex: '#D7261E' },
  { value: 'pandan', label: 'Pandan green', hex: '#2F7D4F' },
  { value: 'kopi', label: 'Kopi brown', hex: '#6B4226' },
  { value: 'laut', label: 'Laut blue', hex: '#1F5F8B' },
  { value: 'bunga', label: 'Bunga pink', hex: '#B02A5B' },
  { value: 'charcoal', label: 'Charcoal', hex: '#1C1A17' },
]

/** Hex for a stored colour name; anything unknown falls back to the default. */
export function shopColourHex(value: string | undefined | null): string {
  return (SHOP_COLOURS.find((c) => c.value === value) ?? SHOP_COLOURS[0]).hex
}
