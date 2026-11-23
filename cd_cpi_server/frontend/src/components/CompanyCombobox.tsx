import { useState, useEffect, useCallback } from "react";
import { Check, ChevronsUpDown, Search, Loader2 } from "lucide-react";
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
import { api } from "@/lib/deals";

export interface CompanyInfo {
  name: string;
  blob_url: string;
  document_count: number;
  library_access_error?: string | null;
}

interface CompanyComboboxProps {
  value: string;
  onChange: (company: CompanyInfo | null) => void;
  className?: string;
}

export function CompanyCombobox({ value, onChange, className }: CompanyComboboxProps) {
  const [open, setOpen] = useState(false);
  const [companies, setCompanies] = useState<CompanyInfo[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchCompanies = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.companies.list();
      setCompanies(data || []);
    } catch (err) {
      console.error("Failed to fetch companies:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCompanies();
    const interval = window.setInterval(fetchCompanies, 10_000);
    return () => window.clearInterval(interval);
  }, [fetchCompanies]);

  const selected = companies.find(c => c.name === value);

  return (
    <Popover
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) fetchCompanies();
      }}
    >
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
            <span className="flex items-center gap-2 truncate font-medium">
              {selected.name}
            </span>
          ) : (
            <span>Select company…</span>
          )}
          {loading ? (
            <Loader2 className="ml-2 h-4 w-4 shrink-0 animate-spin opacity-50" />
          ) : (
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command filter={(val, search) => {
            if (!search) return 1;
            return val.toLowerCase().includes(search.toLowerCase()) ? 1 : 0;
        }}>
          <CommandInput placeholder="Search company name…" />
          <CommandList>
            <CommandEmpty>
              <div className="flex flex-col items-center gap-1 py-2">
                <Search className="h-5 w-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No company found</p>
              </div>
            </CommandEmpty>
            <CommandGroup heading="Available Companies">
              {companies.map((c) => (
                <CommandItem
                  key={c.name}
                  value={c.name}
                  onSelect={() => {
                    onChange(c);
                    setOpen(false);
                  }}
                  className="flex items-center gap-2"
                >
                  <span className="flex flex-col leading-tight">
                    <span className="text-sm font-medium">{c.name}</span>
                    <span className="text-xs text-muted-foreground">
                      {c.library_access_error
                        ? "Mistral Library unavailable"
                        : `${c.document_count} docs`}
                    </span>
                  </span>
                  <Check
                    className={cn(
                      "ml-auto h-4 w-4 shrink-0",
                      value === c.name ? "opacity-100" : "opacity-0",
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
