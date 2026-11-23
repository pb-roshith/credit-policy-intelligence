import { useState } from "react";
import { Check, ChevronsUpDown, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

interface CurrencyEntry {
  code: string;
  name: string;
  symbol: string;
  country: string;
  /** Extra search keywords (e.g. alternate names) */
  keywords?: string;
}

const CURRENCIES: { group: string; items: CurrencyEntry[] }[] = [
  {
    group: "Common",
    items: [
      { code: "INR", name: "Indian Rupee", symbol: "₹", country: "India" },
      { code: "USD", name: "US Dollar", symbol: "$", country: "United States" },
      { code: "EUR", name: "Euro", symbol: "€", country: "European Union", keywords: "europe" },
      { code: "GBP", name: "British Pound", symbol: "£", country: "United Kingdom", keywords: "england sterling" },
      { code: "JPY", name: "Japanese Yen", symbol: "¥", country: "Japan" },
      { code: "CNY", name: "Chinese Yuan", symbol: "¥", country: "China", keywords: "renminbi RMB" },
      { code: "CHF", name: "Swiss Franc", symbol: "Fr", country: "Switzerland" },
    ],
  },
  {
    group: "Asia-Pacific",
    items: [
      { code: "AED", name: "UAE Dirham", symbol: "د.إ", country: "United Arab Emirates", keywords: "dubai abu dhabi" },
      { code: "AUD", name: "Australian Dollar", symbol: "A$", country: "Australia" },
      { code: "BDT", name: "Bangladeshi Taka", symbol: "৳", country: "Bangladesh" },
      { code: "HKD", name: "Hong Kong Dollar", symbol: "HK$", country: "Hong Kong" },
      { code: "IDR", name: "Indonesian Rupiah", symbol: "Rp", country: "Indonesia" },
      { code: "KRW", name: "South Korean Won", symbol: "₩", country: "South Korea", keywords: "korea" },
      { code: "LKR", name: "Sri Lankan Rupee", symbol: "Rs", country: "Sri Lanka" },
      { code: "MYR", name: "Malaysian Ringgit", symbol: "RM", country: "Malaysia" },
      { code: "NPR", name: "Nepalese Rupee", symbol: "Rs", country: "Nepal" },
      { code: "NZD", name: "New Zealand Dollar", symbol: "NZ$", country: "New Zealand" },
      { code: "PHP", name: "Philippine Peso", symbol: "₱", country: "Philippines" },
      { code: "PKR", name: "Pakistani Rupee", symbol: "Rs", country: "Pakistan" },
      { code: "SGD", name: "Singapore Dollar", symbol: "S$", country: "Singapore" },
      { code: "THB", name: "Thai Baht", symbol: "฿", country: "Thailand" },
      { code: "TWD", name: "Taiwan Dollar", symbol: "NT$", country: "Taiwan" },
      { code: "VND", name: "Vietnamese Dong", symbol: "₫", country: "Vietnam" },
    ],
  },
  {
    group: "Americas",
    items: [
      { code: "BRL", name: "Brazilian Real", symbol: "R$", country: "Brazil" },
      { code: "CAD", name: "Canadian Dollar", symbol: "C$", country: "Canada" },
      { code: "MXN", name: "Mexican Peso", symbol: "Mex$", country: "Mexico" },
    ],
  },
  {
    group: "Europe & Africa",
    items: [
      { code: "DKK", name: "Danish Krone", symbol: "kr", country: "Denmark" },
      { code: "NOK", name: "Norwegian Krone", symbol: "kr", country: "Norway" },
      { code: "PLN", name: "Polish Zloty", symbol: "zł", country: "Poland" },
      { code: "SEK", name: "Swedish Krona", symbol: "kr", country: "Sweden" },
      { code: "TRY", name: "Turkish Lira", symbol: "₺", country: "Turkey", keywords: "turkiye" },
      { code: "ZAR", name: "South African Rand", symbol: "R", country: "South Africa" },
    ],
  },
  {
    group: "Middle East",
    items: [
      { code: "BHD", name: "Bahraini Dinar", symbol: "BD", country: "Bahrain" },
      { code: "KWD", name: "Kuwaiti Dinar", symbol: "KD", country: "Kuwait" },
      { code: "OMR", name: "Omani Rial", symbol: "OMR", country: "Oman" },
      { code: "QAR", name: "Qatari Riyal", symbol: "QR", country: "Qatar" },
      { code: "SAR", name: "Saudi Riyal", symbol: "SAR", country: "Saudi Arabia" },
    ],
  },
];

/** Flat lookup for quick access by code */
const CURRENCY_MAP = new Map<string, CurrencyEntry>();
for (const g of CURRENCIES) for (const c of g.items) CURRENCY_MAP.set(c.code, c);

interface CurrencyComboboxProps {
  value: string;
  onChange: (code: string) => void;
  className?: string;
}

export function CurrencyCombobox({ value, onChange, className }: CurrencyComboboxProps) {
  const [open, setOpen] = useState(false);
  const selected = CURRENCY_MAP.get(value);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          className={cn(
            "flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 text-sm shadow-sm transition-colors",
            "hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            !selected && "text-muted-foreground",
            className,
          )}
        >
          {selected ? (
            <span className="flex items-center gap-2 truncate">
              <span className="inline-flex h-5 w-5 items-center justify-center rounded bg-muted text-xs font-semibold">
                {selected.symbol}
              </span>
              <span className="font-medium">{selected.code}</span>
              <span className="text-muted-foreground">— {selected.name}</span>
            </span>
          ) : (
            <span>Select currency…</span>
          )}
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command
          filter={(value, search) => {
            // value is the CommandItem's `value` prop — we stored "code|name|symbol|country|keywords"
            if (!search) return 1;
            const lower = search.toLowerCase();
            return value.toLowerCase().includes(lower) ? 1 : 0;
          }}
        >
          <CommandInput placeholder="Search by country, currency or symbol…" />
          <CommandList>
            <CommandEmpty>
              <div className="flex flex-col items-center gap-1 py-2">
                <Search className="h-5 w-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No currency found</p>
              </div>
            </CommandEmpty>

            {CURRENCIES.map((group) => (
              <CommandGroup key={group.group} heading={group.group}>
                {group.items.map((c) => (
                  <CommandItem
                    key={c.code}
                    // Pack all searchable fields into the value so cmdk can filter on any of them
                    value={`${c.code} ${c.name} ${c.symbol} ${c.country}${c.keywords ? " " + c.keywords : ""}`}
                    onSelect={() => {
                      onChange(c.code);
                      setOpen(false);
                    }}
                    className="flex items-center gap-2"
                  >
                    <span className="inline-flex h-6 w-6 items-center justify-center rounded bg-muted text-xs font-semibold shrink-0">
                      {c.symbol}
                    </span>
                    <span className="flex flex-col leading-tight">
                      <span className="text-sm font-medium">
                        {c.code} <span className="font-normal text-muted-foreground">— {c.name}</span>
                      </span>
                      <span className="text-xs text-muted-foreground">{c.country}</span>
                    </span>
                    <Check
                      className={cn(
                        "ml-auto h-4 w-4 shrink-0",
                        value === c.code ? "opacity-100" : "opacity-0",
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
